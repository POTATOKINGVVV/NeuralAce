from __future__ import annotations

from typing import Dict, List

import numpy as np


class RefereeAuditTrail:
    def audit(
        self,
        state: Dict,
        tracker_diagnostics: Dict | None = None,
        motion_profile: Dict | None = None,
        rally_quality: Dict | None = None,
        confidence_report: Dict | None = None,
    ) -> Dict:
        tracker_diagnostics = tracker_diagnostics or {}
        motion_profile = motion_profile or {}
        rally_quality = rally_quality or {}
        confidence_report = confidence_report or {}

        contradictions = self._collect_contradictions(state, tracker_diagnostics, rally_quality, confidence_report)
        support_signals = self._collect_support_signals(state, tracker_diagnostics, motion_profile, confidence_report)

        referee_confidence = float(state.get("referee_confidence", 0.5) or 0.5)
        landing_confidence = float(state.get("landing_confidence", 0.5) or 0.5)
        direction_consistency = float(state.get("direction_consistency", 0.5) or 0.5)
        calibrated_confidence = float(confidence_report.get("calibrated_confidence", 0.5) or 0.5)
        volatility = float(confidence_report.get("volatility", 0.0) or 0.0)
        signal_integrity = float(tracker_diagnostics.get("signal_integrity", 0.5) or 0.5)
        interpretation_stability = float(rally_quality.get("interpretation_stability", 0.5) or 0.5)

        consistency_score = float(np.clip(
            0.18 * referee_confidence
            + 0.16 * landing_confidence
            + 0.12 * direction_consistency
            + 0.16 * calibrated_confidence
            + 0.12 * signal_integrity
            + 0.12 * interpretation_stability
            + 0.14 * max(0.0, 1.0 - volatility)
            - 0.08 * len(contradictions),
            0.0,
            1.0,
        ))
        verdict_stability = float(np.clip(
            0.42 * calibrated_confidence
            + 0.26 * max(0.0, 1.0 - volatility)
            + 0.18 * interpretation_stability
            + 0.14 * direction_consistency,
            0.0,
            1.0,
        ))
        audit_level = self._audit_level(consistency_score, contradictions)

        return {
            "consistency_score": round(consistency_score, 3),
            "verdict_stability": round(verdict_stability, 3),
            "audit_level": audit_level,
            "contradictions": contradictions,
            "support_signals": support_signals,
            "recommended_action": self._recommended_action(audit_level, state),
            "audit_summary": self._audit_summary(audit_level, consistency_score, verdict_stability, contradictions),
        }

    def _collect_contradictions(
        self,
        state: Dict,
        tracker_diagnostics: Dict,
        rally_quality: Dict,
        confidence_report: Dict,
    ) -> List[str]:
        contradictions: List[str] = []
        auto_result = state.get("auto_result", "UNKNOWN")
        landing_margin = float(state.get("landing_margin", 0.0) or 0.0)
        landing_confidence = float(state.get("landing_confidence", 0.5) or 0.5)
        direction_consistency = float(state.get("direction_consistency", 0.5) or 0.5)
        signal_integrity = float(tracker_diagnostics.get("signal_integrity", 0.5) or 0.5)
        volatility = float(confidence_report.get("volatility", 0.0) or 0.0)
        interpretation_stability = float(rally_quality.get("interpretation_stability", 0.5) or 0.5)

        if auto_result != "UNKNOWN" and float(confidence_report.get("calibrated_confidence", 0.5) or 0.5) < 0.34:
            contradictions.append("校准置信度仍然很低，但已给出明确判定。")
        if abs(landing_margin) < 0.08 and landing_confidence > 0.72:
            contradictions.append("落点边距非常小，但落点置信度异常高。")
        if direction_consistency < 0.38 and auto_result != "UNKNOWN":
            contradictions.append("最后击球方推断较弱，但已给出得分结果。")
        if signal_integrity < 0.35 and interpretation_stability > 0.68:
            contradictions.append("跟踪器信号完整性较差，但回合稳定性报告却较高。")
        if volatility > 0.62 and auto_result in {"WIN", "LOSS"}:
            contradictions.append("判定波动性较高，但给出了明确的胜/负结果。")
        return contradictions

    def _collect_support_signals(
        self,
        state: Dict,
        tracker_diagnostics: Dict,
        motion_profile: Dict,
        confidence_report: Dict,
    ) -> List[str]:
        support_signals: List[str] = []
        if float(state.get("landing_confidence", 0.0) or 0.0) >= 0.62:
            support_signals.append("落点几何足够强，支持当前判定。")
        if float(state.get("direction_consistency", 0.0) or 0.0) >= 0.62:
            support_signals.append("最后击球方方向推断合理一致。")
        if float(tracker_diagnostics.get("signal_integrity", 0.0) or 0.0) >= 0.64:
            support_signals.append("跟踪器信号完整性超过稳定阈值。")
        if float(motion_profile.get("readiness_score", 0.0) or 0.0) >= 0.58:
            support_signals.append("动作就绪度支持交换的物理解读。")
        if float(confidence_report.get("calibrated_confidence", 0.0) or 0.0) >= 0.66:
            support_signals.append("跨模块置信度在校准后仍保持较高。")
        return support_signals

    def _audit_level(self, consistency_score: float, contradictions: List[str]) -> str:
        if consistency_score < 0.42 or len(contradictions) >= 3:
            return "escalate"
        if consistency_score < 0.68 or contradictions:
            return "watch"
        return "clean"

    def _recommended_action(self, audit_level: str, state: Dict) -> str:
        event_name = state.get("event", "回合")
        if audit_level == "escalate":
            return f"将 {event_name} 判定视为临时结果，建议采用保守的反馈用语。"
        if audit_level == "watch":
            return f"保留 {event_name} 判定，但向球员显示注意提示。"
        return f"{event_name} 判定足够稳定，可作为训练信号使用。"

    def _audit_summary(self, audit_level: str, consistency_score: float, verdict_stability: float, contradictions: List[str]) -> str:
        level_label = {"escalate": "升级", "watch": "观察", "clean": "正常"}.get(audit_level, audit_level)
        contradiction_note = "未检测到重大矛盾" if not contradictions else f"标记了 {len(contradictions)} 项矛盾"
        return (
            f"裁判审计级别为{level_label}，一致性 {consistency_score:.2f}，判定稳定性 {verdict_stability:.2f}；"
            f"{contradiction_note}。"
        )
