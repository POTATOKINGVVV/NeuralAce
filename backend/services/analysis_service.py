from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from core.memory.sequence_memory import SequenceMemory
from core.memory.tactic_catalog import TACTIC_SEEDS
from core.memory.tactic_duel_simulator import TacticDuelSimulator
from core.physics.referee_audit import RefereeAuditTrail
from core.physics.uncertainty import ConfidenceCalibrator
from core.utils.match_intelligence import MatchIntelligenceAnalyzer
from core.utils.rally_quality import RallyQualityAnalyzer
from core.utils.report_builder import ReportBuilder
from core.utils.replay_storyline import ReplayStorylineBuilder
from core.utils.training_prescriptor import TrainingPrescriptor
from services.enrichment_service import (
    build_diagnostics_payload,
    build_summary_payload,
    enrich_tactics,
    make_empty_rally_response,
    normalize_advice_payload,
)


class SportStrategy(ABC):
    @abstractmethod
    def process_rally(self, filepath: str, match_type: str) -> Dict:
        pass

    def process_match(self, filepath: str, match_type: str) -> Dict:
        raise NotImplementedError("Match analysis is not implemented for this sport strategy.")


class BadmintonStrategy(SportStrategy):
    def __init__(self, tracker, court_detector, pose_analyzer, physics, rag, coach):
        self.tracker = tracker
        self.court_detector = court_detector
        self.pose_analyzer = pose_analyzer
        self.physics = physics
        self.rag = rag
        self.coach = coach
        self.rally_quality = RallyQualityAnalyzer()
        self.match_intelligence = MatchIntelligenceAnalyzer()
        self.confidence_calibrator = ConfidenceCalibrator()
        self.referee_audit = RefereeAuditTrail()
        self.sequence_memory = SequenceMemory()
        self.duel_simulator = TacticDuelSimulator(TACTIC_SEEDS)
        self.report_builder = ReportBuilder()
        self.replay_storyline = ReplayStorylineBuilder()
        self.training_prescriptor = TrainingPrescriptor()

    def process_rally(self, filepath: str, match_type: str) -> Dict:
        warnings: List[str] = []
        pipeline_status = {
            "court_detection": "pending",
            "tracking": "pending",
            "pose": "pending",
            "physics": "pending",
            "retrieval": "pending",
            "coach": "pending",
        }
        sequence_context = self.sequence_memory.build_context([], match_type=match_type)

        self._prepare_court(filepath, warnings, pipeline_status)

        tracker_diagnostics = {}
        try:
            if hasattr(self.tracker, "infer_detailed"):
                trajectory, fps, tracker_diagnostics = self.tracker.infer_detailed(filepath)
            else:
                trajectory, fps = self.tracker.infer(filepath)
                tracker_diagnostics = getattr(self.tracker, "last_diagnostics", {}) or {}
            pipeline_status["tracking"] = "ok"
        except Exception as error:
            pipeline_status["tracking"] = "failed"
            return make_empty_rally_response(match_type, f"跟踪失败: {error}")

        if not trajectory or len(trajectory) < 2:
            return make_empty_rally_response(match_type, "跟踪返回的点太少，无法分析回合。")

        motion_feedback, motion_profile = self._get_pose_feedback(filepath, warnings, pipeline_status)

        try:
            state = self.physics.analyze_trajectory(trajectory, fps, match_type=match_type)
            pipeline_status["physics"] = "ok"
        except Exception as error:
            pipeline_status["physics"] = "failed"
            return make_empty_rally_response(match_type, f"物理分析失败: {error}")

        state["description"] += f" [动作: {motion_feedback}]"
        auto_result = state.get("auto_result", "UNKNOWN")
        rally_quality = self.rally_quality.evaluate(state, tracker_diagnostics=tracker_diagnostics, motion_profile=motion_profile)
        confidence_report = self.confidence_calibrator.calibrate(state, tracker_diagnostics=tracker_diagnostics, motion_profile=motion_profile, rally_quality=rally_quality)
        referee_audit = self.referee_audit.audit(state, tracker_diagnostics=tracker_diagnostics, motion_profile=motion_profile, rally_quality=rally_quality, confidence_report=confidence_report)
        state["calibrated_confidence"] = confidence_report.get("calibrated_confidence", state.get("referee_confidence", 0.5))
        state["verdict_stability"] = referee_audit.get("verdict_stability", 0.5)

        tactics = self._get_tactics(state, match_type, rally_quality, sequence_context, warnings, pipeline_status)
        duel_projection = self.duel_simulator.simulate(tactics, state, sequence_context=sequence_context)
        advice = self._get_advice(state, tactics, warnings, pipeline_status)

        tactic_id = None
        policy_update = {}
        if tactics:
            metadata = tactics[0].get("metadata", {})
            tactic_id = metadata.get("tactic_id") or metadata.get("id")

        reward = 0.0
        if tactic_id and auto_result != "UNKNOWN":
            try:
                reward = self.physics.calculate_reward(auto_result, trajectory_quality=state.get("trajectory_quality", 0.5), referee_confidence=state.get("referee_confidence", 0.5), pressure_index=state.get("pressure_index", 0.5))
                retrieval_confidence = self._retrieval_confidence(tactics)
                top_tactic = tactics[0] if tactics else {}
                policy_update = self.rag.update_policy(
                    tactic_id,
                    reward,
                    context={
                        "event": state.get("event"),
                        "match_type": match_type,
                        "court_context": state.get("court_context"),
                        "referee_confidence": state.get("referee_confidence", 0.5),
                        "trajectory_quality": state.get("trajectory_quality", 0.5),
                        "retrieval_confidence": retrieval_confidence,
                        "context_score": top_tactic.get("context_score", 0.5),
                        "attack_phase": state.get("attack_phase"),
                        "tempo_profile": state.get("tempo_profile"),
                        "last_hitter": state.get("last_hitter"),
                        "pressure_index": state.get("pressure_index", 0.5),
                        "rally_quality": rally_quality.get("overall_quality", 0.5),
                        "auto_result": auto_result,
                        **sequence_context.get("retrieval_context", {}),
                    },
                ) or {}
            except Exception as error:
                warnings.append(f"策略更新已跳过: {error}")

        summary = build_summary_payload(state, advice, tactics, auto_result)
        diagnostics = build_diagnostics_payload(
            warnings=warnings,
            pipeline_status=pipeline_status,
            motion_feedback=motion_feedback,
            trajectory_points=len(state.get("coordinates", [])),
            tactics=tactics,
            state=state,
            tracker_diagnostics=tracker_diagnostics,
            motion_profile=motion_profile,
            rally_quality=rally_quality,
            confidence_report=confidence_report,
            referee_audit=referee_audit,
            sequence_context=sequence_context,
            duel_projection=duel_projection,
        )
        diagnostics["policy_update"] = policy_update
        training_plan = self.training_prescriptor.build_rally_plan(state, tactics, diagnostics)
        rally_report = self.report_builder.build_rally_report(state, summary, diagnostics, tactics, training_plan=training_plan)

        return {
            "physics": state,
            "advice": advice,
            "tactics": tactics,
            "session_id": tactic_id,
            "match_type": match_type,
            "auto_result": auto_result,
            "auto_reward": reward,
            "summary": summary,
            "diagnostics": diagnostics,
            "report": rally_report,
        }

    def process_match(self, filepath: str, match_type: str) -> Dict:
        warnings: List[str] = []
        self._prepare_court(filepath, warnings, {})

        try:
            full_trajectory, fps = self.tracker.infer(filepath)
        except Exception as error:
            return {
                "status": "failed",
                "match_summary": {"total_rallies_found": 0, "valid_rallies_analyzed": 0, "intelligence": {}, "report": {}},
                "timeline": [],
                "warnings": [f"Tracking failed: {error}"],
            }

        cap = cv2.VideoCapture(filepath)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()

        fsm = self._build_fsm(fps, width, height)
        for frame_index, coordinate in enumerate(full_trajectory):
            fsm.update(frame_index, coordinate)

        rally_segments = fsm.get_segments()
        segment_summaries = fsm.get_segment_summaries() if hasattr(fsm, "get_segment_summaries") else []
        timeline = []
        for rally_index, rally_trajectory in enumerate(rally_segments, start=1):
            if len(rally_trajectory) < 3:
                continue
            sequence_context = self.sequence_memory.build_context(timeline, match_type=match_type)
            segment_summary = segment_summaries[rally_index - 1] if rally_index - 1 < len(segment_summaries) else {}
            timeline_item = self._analyze_rally_segment(
                rally_index=rally_index,
                rally_trajectory=rally_trajectory,
                fps=fps,
                match_type=match_type,
                tracker_diagnostics=segment_summary,
                sequence_context=sequence_context,
            )
            if timeline_item:
                timeline.append(timeline_item)

        sequence_context = self.sequence_memory.build_context(timeline, match_type=match_type)
        duel_summary = self.duel_simulator.summarize_matchup(timeline, sequence_context=sequence_context)
        intelligence = self.match_intelligence.summarize(timeline, match_type, sequence_context=sequence_context, duel_summary=duel_summary)
        replay_story = self.replay_storyline.build(timeline, intelligence, sequence_context=sequence_context, duel_summary=duel_summary)
        match_training_plan = self.training_prescriptor.build_match_plan(intelligence, timeline)
        match_report = self.report_builder.build_match_report(
            intelligence,
            timeline,
            training_plan=match_training_plan,
            sequence_context=sequence_context,
            duel_summary=duel_summary,
            replay_story=replay_story,
        )
        return {
            "status": "success",
            "match_summary": {
                "total_rallies_found": len(rally_segments),
                "valid_rallies_analyzed": len(timeline),
                "intelligence": intelligence,
                "sequence_memory": sequence_context,
                "duel_summary": duel_summary,
                "replay_story": replay_story,
                "report": match_report,
            },
            "timeline": timeline,
            "warnings": warnings,
        }

    def _prepare_court(self, filepath: str, warnings: List[str], pipeline_status: Dict[str, str]):
        try:
            cap = cv2.VideoCapture(filepath)
            ret, frame0 = cap.read()
            cap.release()
            if not ret or frame0 is None:
                warnings.append("无法读取第一帧用于场地检测。")
                if "court_detection" in pipeline_status:
                    pipeline_status["court_detection"] = "skipped"
                return

            corners = self.court_detector.detect(frame0)
            self.physics.update_homography(corners)
            if "court_detection" in pipeline_status:
                pipeline_status["court_detection"] = "ok"
        except Exception as error:
            warnings.append(f"场地检测回退到默认映射: {error}")
            if "court_detection" in pipeline_status:
                pipeline_status["court_detection"] = "fallback"

    def _get_pose_feedback(self, filepath: str, warnings: List[str], pipeline_status: Dict[str, str]):
        try:
            pose_sequence = self.pose_analyzer.infer(filepath)
            if hasattr(self.pose_analyzer, "evaluate_motion_profile"):
                motion_profile = self.pose_analyzer.evaluate_motion_profile(pose_sequence)
                motion_feedback = motion_profile.get("feedback_text", "姿态分析不可用。")
            else:
                motion_feedback = self.pose_analyzer.evaluate_motion(pose_sequence)
                motion_profile = {}
            pipeline_status["pose"] = "ok"
            return motion_feedback, motion_profile
        except Exception as error:
            warnings.append(f"姿态分析不可用: {error}")
            pipeline_status["pose"] = "fallback"
            return "姿态分析不可用。", {}

    def _get_tactics(self, state: Dict, match_type: str, rally_quality: Dict, sequence_context: Dict, warnings: List[str], pipeline_status: Dict[str, str]) -> List[Dict]:
        try:
            query_text = f"[{match_type}] {state['description']}"
            retrieval_context = {
                "event": state.get("event"),
                "max_speed_kmh": state.get("max_speed_kmh", 0.0),
                "match_type": match_type,
                "court_context": state.get("court_context"),
                "auto_result": state.get("auto_result"),
                "trajectory_quality": state.get("trajectory_quality", 0.5),
                "referee_confidence": state.get("referee_confidence", 0.5),
                "attack_phase": state.get("attack_phase", "neutral"),
                "tempo_profile": state.get("tempo_profile", "medium"),
                "last_hitter": state.get("last_hitter", "UNKNOWN"),
                "pressure_index": state.get("pressure_index", 0.5),
                "rally_quality": rally_quality.get("overall_quality", 0.5),
                **sequence_context.get("retrieval_context", {}),
            }
            tactics = self.rag.retrieve(query_text, context=retrieval_context)
            pipeline_status["retrieval"] = "ok" if tactics else "empty"
            return enrich_tactics(state, tactics)
        except Exception as error:
            warnings.append(f"战术检索不可用: {error}")
            pipeline_status["retrieval"] = "fallback"
            return []

    def _get_advice(self, state: Dict, tactics: List[Dict], warnings: List[str], pipeline_status: Dict[str, str]) -> Dict:
        try:
            raw_advice = self.coach.generate_structured_advice(state, tactics)
            pipeline_status["coach"] = "ok"
        except Exception as error:
            warnings.append(f"教练生成回退到默认值: {error}")
            pipeline_status["coach"] = "fallback"
            raw_advice = None
        return normalize_advice_payload(raw_advice, tactics, state)

    def _build_fsm(self, fps: float, width: int, height: int):
        from core.utils.fsm_segmenter import BadmintonFSM

        return BadmintonFSM(fps=fps, width=width, height=height)

    def _analyze_rally_segment(self, rally_index: int, rally_trajectory: List[Tuple[int, int]], fps: float, match_type: str, tracker_diagnostics: Dict | None = None, sequence_context: Dict | None = None) -> Optional[Dict]:
        warnings: List[str] = []
        pipeline_status = {"tracking": "segment", "pose": "not_available", "physics": "pending", "retrieval": "pending", "coach": "pending"}
        tracker_diagnostics = tracker_diagnostics or {}
        sequence_context = sequence_context or self.sequence_memory.build_context([], match_type=match_type)

        try:
            state = self.physics.analyze_trajectory(rally_trajectory, fps, match_type)
            pipeline_status["physics"] = "ok"
        except Exception:
            return None

        if state["max_speed_kmh"] < 30:
            return None

        motion_feedback = "姿态分析仅针对短回合片段计算。"
        motion_profile = {"quality_label": "segment-only", "readiness_score": 0.45}
        state["description"] += f" [动作: {motion_feedback}]"
        auto_result = state.get("auto_result", "UNKNOWN")
        rally_quality = self.rally_quality.evaluate(state, tracker_diagnostics=tracker_diagnostics, motion_profile=motion_profile)
        confidence_report = self.confidence_calibrator.calibrate(state, tracker_diagnostics=tracker_diagnostics, motion_profile=motion_profile, rally_quality=rally_quality)
        referee_audit = self.referee_audit.audit(state, tracker_diagnostics=tracker_diagnostics, motion_profile=motion_profile, rally_quality=rally_quality, confidence_report=confidence_report)
        state["calibrated_confidence"] = confidence_report.get("calibrated_confidence", state.get("referee_confidence", 0.5))
        state["verdict_stability"] = referee_audit.get("verdict_stability", 0.5)
        tactics = self._get_tactics(state, match_type, rally_quality, sequence_context, warnings, pipeline_status)
        duel_projection = self.duel_simulator.simulate(tactics, state, sequence_context=sequence_context)
        advice = self._get_advice(state, tactics, warnings, pipeline_status)

        reward = 0.0
        policy_update = {}
        if tactics:
            tactic_id = tactics[0].get("metadata", {}).get("tactic_id")
            if tactic_id and auto_result != "UNKNOWN":
                try:
                    reward = self.physics.calculate_reward(auto_result, trajectory_quality=state.get("trajectory_quality", 0.5), referee_confidence=state.get("referee_confidence", 0.5), pressure_index=state.get("pressure_index", 0.5))
                    retrieval_confidence = self._retrieval_confidence(tactics)
                    top_tactic = tactics[0]
                    policy_update = self.rag.update_policy(
                        tactic_id,
                        reward,
                        context={
                            "event": state.get("event"),
                            "match_type": match_type,
                            "court_context": state.get("court_context"),
                            "referee_confidence": state.get("referee_confidence", 0.5),
                            "trajectory_quality": state.get("trajectory_quality", 0.5),
                            "retrieval_confidence": retrieval_confidence,
                            "context_score": top_tactic.get("context_score", 0.5),
                            "attack_phase": state.get("attack_phase"),
                            "tempo_profile": state.get("tempo_profile"),
                            "last_hitter": state.get("last_hitter"),
                            "pressure_index": state.get("pressure_index", 0.5),
                            "rally_quality": rally_quality.get("overall_quality", 0.5),
                            "auto_result": auto_result,
                            **sequence_context.get("retrieval_context", {}),
                        },
                    ) or {}
                except Exception as error:
                    warnings.append(f"策略更新已跳过: {error}")

        summary = build_summary_payload(state, advice, tactics, auto_result)
        diagnostics = build_diagnostics_payload(
            warnings=warnings,
            pipeline_status=pipeline_status,
            motion_feedback=motion_feedback,
            trajectory_points=len(state.get("coordinates", [])),
            tactics=tactics,
            state=state,
            tracker_diagnostics=tracker_diagnostics,
            motion_profile=motion_profile,
            rally_quality=rally_quality,
            confidence_report=confidence_report,
            referee_audit=referee_audit,
            sequence_context=sequence_context,
            duel_projection=duel_projection,
        )
        diagnostics["policy_update"] = policy_update
        training_plan = self.training_prescriptor.build_rally_plan(state, tactics, diagnostics)
        rally_report = self.report_builder.build_rally_report(state, summary, diagnostics, tactics, training_plan=training_plan)

        return {
            "rally_index": rally_index,
            "duration_sec": round(len(rally_trajectory) / fps, 2),
            "physics": state,
            "advice": advice,
            "tactics": tactics,
            "auto_result": auto_result,
            "auto_reward": reward,
            "summary": summary,
            "diagnostics": diagnostics,
            "report": rally_report,
        }

    def _retrieval_confidence(self, tactics: List[Dict]) -> float:
        if not tactics:
            return 0.35
        top_score = float(tactics[0].get("score", 0.0))
        rerank_score = float(tactics[0].get("rerank_score", top_score) or top_score)
        context_score = float(tactics[0].get("context_score", 0.0))
        scenario_bias = float(tactics[0].get("scenario_bias", 0.0))
        graph_bias = float(tactics[0].get("graph_bias", 0.0))
        continuity_score = float(tactics[0].get("continuity_score", 0.5) or 0.5)
        coverage_score = float(tactics[0].get("coverage_score", 0.5) or 0.5)
        scheduler_profile = tactics[0].get("scheduler_profile", {}) or {}
        exploitation = float(scheduler_profile.get("exploitation_weight", 0.5) or 0.5)
        return max(0.35, min(0.2 * top_score + 0.18 * rerank_score + 0.14 * context_score + 0.12 * continuity_score + 0.1 * coverage_score + 0.06 * min(scenario_bias * 10, 1.0) + 0.06 * min(graph_bias * 10, 1.0) + 0.14 * exploitation, 1.0))


class TableTennisStrategy(SportStrategy):
    def __init__(self, tracker, court_detector, pose_analyzer, physics, rag, coach):
        self.tracker = tracker
        self.court_detector = court_detector
        self.pose_analyzer = pose_analyzer
        self.physics = physics
        self.rag = rag
        self.coach = coach
        self._init_error: Optional[str] = None
        self.tt_tracker = None
        self.table_detector = None
        self.table_referee = None

        try:
            from core.physics.table_referee import TableTennisReferee
            from core.vision.table_detector import TableDetector
            from core.vision.table_tennis_tracker import TableTennisTracker

            self.tt_tracker = TableTennisTracker()
            self.table_detector = TableDetector()
            self.table_referee = TableTennisReferee()
        except Exception as error:
            self._init_error = str(error)

    def process_rally(self, filepath: str, match_type: str) -> Dict:
        if self._init_error:
            print(f"[TT-Pipeline] ABORT: init error = {self._init_error}")
            return make_empty_rally_response(match_type, f"乒乓球模块初始化失败: {self._init_error}")

        warnings: List[str] = []
        pipeline_status = {
            "court_detection": "pending",
            "tracking": "pending",
            "pose": "skipped",
            "physics": "pending",
            "retrieval": "pending",
            "coach": "pending",
        }

        frame0 = self._read_first_frame(filepath)
        if frame0 is None:
            print("[TT-Pipeline] ABORT: could not read first frame")
            pipeline_status["court_detection"] = "failed"
            return make_empty_rally_response(match_type, "无法读取第一帧用于球台检测。")

        detection = self.table_detector.detect_with_net(frame0)
        corners = detection.get("corners")
        net_line = detection.get("net_line")
        if corners is None or net_line is None:
            print(f"[TT-Pipeline] ABORT: table detection failed (corners={corners is not None}, net_line={net_line is not None})")
            pipeline_status["court_detection"] = "failed"
            return make_empty_rally_response(match_type, "球台检测未能提供有效的角点/网线。")
        print(f"[TT-Pipeline] Table detected OK, corners shape={corners.shape}")
        pipeline_status["court_detection"] = "ok"

        tracker_diagnostics = {}
        try:
            trajectory, fps, tracker_diagnostics = self.tt_tracker.infer_detailed(filepath)
            pipeline_status["tracking"] = "ok"
        except Exception as error:
            print(f"[TT-Pipeline] ABORT: tracking exception = {error}")
            pipeline_status["tracking"] = "failed"
            return make_empty_rally_response(match_type, f"乒乓球跟踪失败: {error}")

        visible = sum(1 for x, y in trajectory if x > 0 or y > 0)
        print(f"[TT-Pipeline] Tracking OK: {len(trajectory)} frames, {visible} visible, fps={fps}")

        if not trajectory or len(trajectory) < 2:
            print("[TT-Pipeline] ABORT: trajectory too short")
            return make_empty_rally_response(match_type, "跟踪返回的点太少，无法分析回合。")

        try:
            state = self._build_state(trajectory, fps, corners, net_line, match_type)
            pipeline_status["physics"] = "ok"
        except Exception as error:
            pipeline_status["physics"] = "failed"
            return make_empty_rally_response(match_type, f"乒乓球裁判分析失败: {error}")

        tactics = self._get_tactics(state, match_type, warnings, pipeline_status)
        advice = self._get_advice(state, tactics, warnings, pipeline_status)

        auto_result = state.get("auto_result", "UNKNOWN")
        tactic_id = None
        policy_update = {}
        if tactics:
            metadata = tactics[0].get("metadata", {})
            tactic_id = metadata.get("tactic_id") or metadata.get("id")

        reward = 0.0
        if tactic_id and auto_result != "UNKNOWN":
            try:
                reward = self.physics.calculate_reward(
                    auto_result,
                    trajectory_quality=state.get("trajectory_quality", 0.5),
                    referee_confidence=state.get("referee_confidence", 0.5),
                    pressure_index=state.get("pressure_index", 0.5),
                )
                policy_update = self.rag.update_policy(
                    tactic_id,
                    reward,
                    context={
                        "event": state.get("event"),
                        "match_type": match_type,
                        "court_context": state.get("court_context"),
                        "referee_confidence": state.get("referee_confidence", 0.5),
                        "trajectory_quality": state.get("trajectory_quality", 0.5),
                        "pressure_index": state.get("pressure_index", 0.5),
                        "auto_result": auto_result,
                    },
                    sport_type="table_tennis",
                ) or {}
            except Exception as error:
                warnings.append(f"策略更新已跳过: {error}")

        summary = build_summary_payload(state, advice, tactics, auto_result)
        diagnostics = build_diagnostics_payload(
            warnings=warnings,
            pipeline_status=pipeline_status,
            motion_feedback="姿态分析当前在乒乓球策略中未启用。",
            trajectory_points=len(state.get("coordinates", [])),
            tactics=tactics,
            state=state,
            tracker_diagnostics=tracker_diagnostics,
        )
        diagnostics["policy_update"] = policy_update

        return {
            "physics": state,
            "advice": advice,
            "tactics": tactics,
            "session_id": tactic_id,
            "match_type": match_type,
            "sport_type": "table_tennis",
            "auto_result": auto_result,
            "auto_reward": reward,
            "summary": summary,
            "diagnostics": diagnostics,
            "report": {},
        }

    def process_match(self, filepath: str, match_type: str) -> Dict:
        return {
            "status": "failed",
            "sport_type": "table_tennis",
            "match_summary": {
                "total_rallies_found": 0,
                "valid_rallies_analyzed": 0,
                "intelligence": {},
                "report": {},
            },
            "timeline": [],
            "warnings": ["Table tennis match-level segmentation is not implemented yet."],
        }

    @staticmethod
    def _read_first_frame(filepath: str):
        cap = cv2.VideoCapture(filepath)
        ok, frame0 = cap.read()
        cap.release()
        if not ok or frame0 is None:
            return None
        return frame0

    def _build_state(
        self,
        trajectory: List[Tuple[int, int]],
        fps: float,
        corners,
        net_line,
        match_type: str,
    ) -> Dict:
        referee_state = self.table_referee.evaluate_rally(
            trajectory=trajectory,
            fps=fps,
            corners=corners,
            net_line=net_line,
            match_type=match_type,
        )

        valid_points = [(x, y) for x, y in trajectory if x > 0 or y > 0]
        speed_stats = self._compute_speed_stats(valid_points, fps, corners)
        visibility_ratio = len(valid_points) / max(len(trajectory), 1)
        bounce_count = int(referee_state.get("bounce_count", 0))

        state = {
            **referee_state,
            "event": self._classify_tt_event(speed_stats, bounce_count, referee_state),
            "max_speed_kmh": round(speed_stats["max"], 2),
            "mean_speed_kmh": round(speed_stats["mean"], 2),
            "end_speed_kmh": round(speed_stats["end"], 2),
            "pressure_index": round(min(1.0, 0.35 + 0.12 * bounce_count), 3),
            "trajectory_quality": round(float(visibility_ratio), 3),
            "coordinates": trajectory,
            "attack_phase": "under_pressure" if bounce_count >= 3 else "neutral",
            "tempo_profile": self._tempo_profile(speed_stats["max"]),
            "shot_shape": self._classify_shot_shape(valid_points, bounce_count),
            "last_bounce_side": self._last_bounce_side(referee_state),
            "description": (
                f"\u68c0\u6d4b\u5230 {bounce_count} \u6b21\u5f39\u8df3\uff0c\u81ea\u52a8\u7ed3\u679c\u4e3a {referee_state.get('auto_result', 'UNKNOWN')}\uff0c"
                f"\u4e52\u4e53\u7403\u56de\u5408\u3002"
            ),
        }
        return state

    @staticmethod
    def _compute_speed_stats(
        points: List[Tuple[int, int]],
        fps: float,
        corners: np.ndarray,
    ) -> Dict:
        """Compute max / mean / end speed in km/h using a homography
        derived from the detected table corners and standard table dimensions.

        Falls back to a pixel-ratio heuristic if the homography cannot be
        computed (e.g. degenerate corners).
        """
        from config import TABLE_LENGTH, TABLE_WIDTH

        zero = {"max": 0.0, "mean": 0.0, "end": 0.0}
        if len(points) < 2 or fps <= 0:
            return zero

        # Build homography: pixel corners → real-world metres
        dst_pts = np.array(
            [[0, 0], [TABLE_WIDTH, 0], [TABLE_WIDTH, TABLE_LENGTH], [0, TABLE_LENGTH]],
            dtype=np.float32,
        )
        try:
            src_pts = np.array(corners, dtype=np.float32).reshape(4, 2)
            H, _ = cv2.findHomography(src_pts, dst_pts)
            if H is None:
                raise ValueError("degenerate homography")
        except Exception:
            # Fallback: rough px→m using table diagonal
            diag_px = float(np.linalg.norm(corners[2] - corners[0])) or 1.0
            diag_m = (TABLE_LENGTH ** 2 + TABLE_WIDTH ** 2) ** 0.5
            px_to_m = diag_m / diag_px
            H = None

        # Convert all points to world coordinates
        pts_px = np.array(points, dtype=np.float32).reshape(-1, 1, 2)
        if H is not None:
            pts_world = cv2.perspectiveTransform(pts_px, H).reshape(-1, 2)
        else:
            pts_world = pts_px.reshape(-1, 2) * px_to_m

        # Per-frame speeds
        diffs = np.diff(pts_world, axis=0)  # (N-1, 2)
        dists_m = np.linalg.norm(diffs, axis=1)  # metres per frame
        speeds_ms = dists_m * fps  # m/s
        speeds_kmh = speeds_ms * 3.6

        # Filter out implausible spikes (> 200 km/h for table tennis)
        plausible = speeds_kmh[speeds_kmh <= 200.0]
        if len(plausible) == 0:
            plausible = speeds_kmh  # keep raw if all look high

        max_speed = float(np.max(plausible)) if len(plausible) else 0.0
        mean_speed = float(np.mean(plausible)) if len(plausible) else 0.0

        # End speed: average of last 20% of frames
        tail_n = max(1, len(speeds_kmh) // 5)
        end_speed = float(np.mean(speeds_kmh[-tail_n:])) if len(speeds_kmh) else 0.0

        return {"max": max_speed, "mean": mean_speed, "end": end_speed}

    @staticmethod
    def _tempo_profile(max_speed_kmh: float) -> str:
        if max_speed_kmh >= 75:
            return "fast"
        if max_speed_kmh >= 40:
            return "medium"
        return "slow"

    @staticmethod
    def _classify_shot_shape(
        points: List[Tuple[int, int]],
        bounce_count: int,
    ) -> str:
        """Infer shot shape from trajectory curvature and vertical arc.

        Heuristics (pixel-space, camera-agnostic):
        * **topspin-loop** – pronounced downward acceleration after apex
          (large positive second derivative of y).
        * **backspin-chop** – shallow arc with slow y-change after bounce.
        * **flat-smash** – very high horizontal speed, minimal arc.
        * **push-control** – short displacement, low speed.
        * **flat-rally** – fallback for everything else.
        """
        if len(points) < 6:
            return "flat-rally"

        pts = np.array(points, dtype=np.float64)
        dy = np.diff(pts[:, 1])  # first derivative of y
        ddy = np.diff(dy)         # second derivative of y

        # Displacement and speed proxies
        total_dx = abs(pts[-1, 0] - pts[0, 0])
        total_dy = abs(pts[-1, 1] - pts[0, 1])
        mean_abs_speed = float(np.mean(np.abs(np.diff(pts, axis=0)), axis=0).sum())

        # Curvature: mean of absolute second derivative
        mean_curvature = float(np.mean(np.abs(ddy))) if len(ddy) > 0 else 0.0

        # Ratio of downward acceleration segments (positive ddy = ball curving down)
        down_accel_ratio = float(np.mean(ddy > 0.5)) if len(ddy) > 0 else 0.0

        # Classification
        if mean_abs_speed > 15 and mean_curvature < 1.5 and total_dy < total_dx * 0.4:
            return "flat-smash"
        if down_accel_ratio > 0.55 and mean_curvature > 2.0:
            return "topspin-loop"
        if down_accel_ratio < 0.35 and mean_curvature > 1.2:
            return "backspin-chop"
        if mean_abs_speed < 5 and total_dx < 80 and total_dy < 60:
            return "push-control"
        return "flat-rally"

    @staticmethod
    def _classify_tt_event(
        speed_stats: Dict,
        bounce_count: int,
        referee_state: Dict,
    ) -> str:
        """Classify the table-tennis rally into a named event type.

        Categories:
        * **Serve & Attack** – few bounces, first bounce confidence high.
        * **Fast Attack Winner** – high max speed, decisive result.
        * **Extended Rally** – many bounces, alternating sides.
        * **Short Control** – low speed, short displacement.
        * **Table Tennis Rally** – fallback.
        """
        max_spd = speed_stats.get("max", 0.0)
        mean_spd = speed_stats.get("mean", 0.0)
        auto_result = referee_state.get("auto_result", "UNKNOWN")
        bounces = referee_state.get("bounces", []) or []

        if bounce_count <= 2 and len(bounces) >= 1:
            first_conf = bounces[0].get("confidence", 0) if bounces else 0
            if first_conf > 0.4:
                return "发球抢攻"

        if max_spd >= 70 and auto_result in ("WIN", "LOSS", "FAULT"):
            return "快攻得分"

        if bounce_count >= 4:
            return "多拍相持"

        if mean_spd < 25 and bounce_count <= 3:
            return "短球控制"

        return "乒乓球回合"

    @staticmethod
    def _last_bounce_side(state: Dict) -> str:
        bounces = state.get("bounces", []) or []
        if not bounces:
            return "N/A"
        return bounces[-1].get("side", "N/A")

    def _get_tactics(self, state: Dict, match_type: str, warnings: List[str], pipeline_status: Dict[str, str]) -> List[Dict]:
        try:
            query_text = f"[{match_type}] {state.get('description', '')}"
            retrieval_context = {
                "event": state.get("event"),
                "max_speed_kmh": state.get("max_speed_kmh", 0.0),
                "match_type": match_type,
                "court_context": state.get("court_context"),
                "auto_result": state.get("auto_result"),
                "trajectory_quality": state.get("trajectory_quality", 0.5),
                "referee_confidence": state.get("referee_confidence", 0.5),
                "attack_phase": state.get("attack_phase", "neutral"),
                "tempo_profile": state.get("tempo_profile", "medium"),
                "last_hitter": state.get("last_hitter", "UNKNOWN"),
                "pressure_index": state.get("pressure_index", 0.5),
            }
            tactics = self.rag.retrieve(
                query_text,
                context=retrieval_context,
                sport_type="table_tennis",
            )
            pipeline_status["retrieval"] = "ok" if tactics else "empty"
            return enrich_tactics(state, tactics)
        except Exception as error:
            warnings.append(f"战术检索不可用: {error}")
            pipeline_status["retrieval"] = "fallback"
            return []

    def _get_advice(self, state: Dict, tactics: List[Dict], warnings: List[str], pipeline_status: Dict[str, str]) -> Dict:
        try:
            raw_advice = self.coach.generate_structured_advice(
                state,
                tactics,
                sport_type="table_tennis",
            )
            pipeline_status["coach"] = "ok"
        except Exception as error:
            warnings.append(f"教练生成回退到默认值: {error}")
            pipeline_status["coach"] = "fallback"
            raw_advice = self.coach._fallback_payload(state, tactics, sport_type="table_tennis")
        return normalize_advice_payload(raw_advice, tactics, state)


class AnalysisService:
    def __init__(self, tracker, court_detector, pose_analyzer, physics, rag, coach):
        self._dependencies = {
            "tracker": tracker,
            "court_detector": court_detector,
            "pose_analyzer": pose_analyzer,
            "physics": physics,
            "rag": rag,
            "coach": coach,
        }
        self._strategy_factories = {
            "badminton": BadmintonStrategy,
            "table_tennis": TableTennisStrategy,
        }
        self._sport_type: Optional[str] = None
        self._strategy: Optional[SportStrategy] = None

    def for_sport(self, sport_type: str) -> "AnalysisService":
        self._sport_type = sport_type
        return self

    def __enter__(self) -> "AnalysisService":
        if not self._sport_type:
            raise ValueError("sport_type must be provided before entering AnalysisService context.")
        self._strategy = self._create_strategy(self._sport_type)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self._strategy = None
        self._sport_type = None

    def _create_strategy(self, sport_type: str) -> SportStrategy:
        strategy_cls = self._strategy_factories.get(sport_type)
        if strategy_cls is None:
            raise ValueError(f"Unsupported sport_type: {sport_type}")
        return strategy_cls(**self._dependencies)

    def process_rally(self, filepath: str, match_type: str) -> Dict:
        if self._strategy is None:
            raise RuntimeError("No active sport strategy. Use AnalysisService as a context manager with for_sport().")
        return self._strategy.process_rally(filepath, match_type)

    def process_match(self, filepath: str, match_type: str) -> Dict:
        if self._strategy is None:
            raise RuntimeError("No active sport strategy. Use AnalysisService as a context manager with for_sport().")
        return self._strategy.process_match(filepath, match_type)

    def analyze_rally(self, filepath: str, match_type: str, sport_type: str = "badminton") -> Dict:
        with self.for_sport(sport_type) as context:
            return context.process_rally(filepath, match_type)

    def analyze_match(self, filepath: str, match_type: str, sport_type: str = "badminton") -> Dict:
        with self.for_sport(sport_type) as context:
            return context.process_match(filepath, match_type)
