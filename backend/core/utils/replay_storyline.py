from __future__ import annotations

from typing import Dict, List

import numpy as np

from core.utils.label_zh import zh

_RESULT_MAP = {"WIN": "胜", "LOSS": "负", "UNKNOWN": "未知"}
_MOMENTUM_MAP = {"surging": "上升势头", "under-pressure": "被动", "neutral": "中性"}


class ReplayStorylineBuilder:
    def build(self, timeline: List[Dict], intelligence: Dict, sequence_context: Dict | None = None, duel_summary: Dict | None = None) -> Dict:
        sequence_context = sequence_context or {}
        duel_summary = duel_summary or {}
        if not timeline:
            return {
                "opening_phase": {},
                "turning_points": [],
                "adaptation_cycles": [],
                "critical_rallies": [],
                "closing_state": {},
                "storyline_cards": [],
                "timeline_digest": [],
                "replay_summary": "暂无回放故事线。",
            }

        opening_phase = self._opening_phase(timeline[: min(3, len(timeline))])
        turning_points = self._turning_points(timeline)
        adaptation_cycles = self._adaptation_cycles(timeline, sequence_context)
        critical_rallies = self._critical_rallies(timeline)
        closing_state = self._closing_state(timeline[-1], intelligence, duel_summary)
        timeline_digest = self._timeline_digest(timeline)
        storyline_cards = self._storyline_cards(opening_phase, turning_points, adaptation_cycles, closing_state)

        return {
            "opening_phase": opening_phase,
            "turning_points": turning_points,
            "adaptation_cycles": adaptation_cycles,
            "critical_rallies": critical_rallies,
            "closing_state": closing_state,
            "storyline_cards": storyline_cards,
            "timeline_digest": timeline_digest,
            "replay_summary": self._summary(opening_phase, turning_points, closing_state),
        }

    def _opening_phase(self, opening_items: List[Dict]) -> Dict:
        if not opening_items:
            return {}
        events = [item.get("physics", {}).get("event", "未知") for item in opening_items]
        tactics = [
            (item.get("tactics") or [{}])[0].get("name", "未知")
            for item in opening_items
            if item.get("tactics")
        ]
        avg_pressure = float(np.mean([float(item.get("physics", {}).get("pressure_index", 0.0) or 0.0) for item in opening_items]))
        return {
            "headline": "开局阶段",
            "events": events,
            "tactics": tactics,
            "average_pressure": round(avg_pressure, 3),
            "summary": f"比赛以 {' / '.join(events[:2]) if events else '未知模式'} 开局，平均压力 {avg_pressure:.2f}。",
        }

    def _turning_points(self, timeline: List[Dict]) -> List[Dict]:
        turning_points = []
        if len(timeline) < 2:
            return turning_points
        pressures = [float(item.get("physics", {}).get("pressure_index", 0.0) or 0.0) for item in timeline]
        mean_pressure = float(np.mean(pressures)) if pressures else 0.0
        std_pressure = float(np.std(pressures)) if len(pressures) > 1 else 0.0
        threshold = mean_pressure + std_pressure

        for previous, current in zip(timeline, timeline[1:]):
            prev_result = previous.get("auto_result", "UNKNOWN")
            curr_result = current.get("auto_result", "UNKNOWN")
            prev_tactic = (previous.get("tactics") or [{}])[0].get("name", "未知") if previous.get("tactics") else "未知"
            curr_tactic = (current.get("tactics") or [{}])[0].get("name", "未知") if current.get("tactics") else "未知"
            current_pressure = float(current.get("physics", {}).get("pressure_index", 0.0) or 0.0)
            if curr_result != prev_result or current_pressure >= threshold or curr_tactic != prev_tactic:
                turning_points.append(
                    {
                        "rally_index": current.get("rally_index"),
                        "trigger": self._turning_trigger(prev_result, curr_result, prev_tactic, curr_tactic, current_pressure, threshold),
                        "summary": current.get("summary", {}).get("headline", "回合转折"),
                    }
                )
        return turning_points[:4]

    def _adaptation_cycles(self, timeline: List[Dict], sequence_context: Dict) -> List[Dict]:
        transitions = sequence_context.get("tactic_transitions", []) or []
        cycles = []
        for transition in transitions[:3]:
            cycles.append(
                {
                    "from": transition.get("from", "未知"),
                    "to": transition.get("to", "未知"),
                    "style_shift": transition.get("style_shift", "balanced -> balanced"),
                    "summary": f"序列从 {transition.get('from', '未知')} 演变为 {transition.get('to', '未知')}。"
                }
            )
        if not cycles and timeline:
            latest = timeline[-1]
            cycles.append(
                {
                    "from": "开局读取",
                    "to": (latest.get("tactics") or [{}])[0].get("name", "未知") if latest.get("tactics") else "未知",
                    "style_shift": "single-anchor",
                    "summary": "可用时间线太短，无法完成完整适应循环，最新回合作为当前锚点。",
                }
            )
        return cycles

    def _critical_rallies(self, timeline: List[Dict]) -> List[Dict]:
        scored = []
        for item in timeline:
            pressure = float(item.get("physics", {}).get("pressure_index", 0.0) or 0.0)
            duel_risk = float(((item.get("diagnostics", {}) or {}).get("duel_projection", {}) or {}).get("duel_risk", 0.0) or 0.0)
            reward = abs(float(item.get("auto_reward", 0.0) or 0.0))
            score = 0.42 * pressure + 0.28 * duel_risk + 0.3 * min(reward / 10.0, 1.0)
            scored.append((score, item))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        critical = []
        for score, item in scored[:3]:
            critical.append(
                {
                    "rally_index": item.get("rally_index"),
                    "score": round(score, 3),
                    "headline": item.get("summary", {}).get("headline", "关键回合"),
                    "takeaway": item.get("summary", {}).get("key_takeaway", ""),
                }
            )
        return critical

    def _closing_state(self, last_item: Dict, intelligence: Dict, duel_summary: Dict) -> Dict:
        last_tactic = (last_item.get("tactics") or [{}])[0].get("name", "未知") if last_item.get("tactics") else "未知"
        return {
            "last_rally_index": last_item.get("rally_index"),
            "verdict": last_item.get("auto_result", "UNKNOWN"),
            "tactic_anchor": last_tactic,
            "momentum_state": intelligence.get("momentum_state", "neutral"),
            "dominant_duel": duel_summary.get("dominant_duel", "不可用"),
            "summary": f"回放以 {last_tactic} 作为最新锚点结束，势头状态为 {_MOMENTUM_MAP.get(intelligence.get('momentum_state', 'neutral'), intelligence.get('momentum_state', 'neutral'))}。",
        }

    def _timeline_digest(self, timeline: List[Dict]) -> List[Dict]:
        digest = []
        for item in timeline:
            tactic = (item.get("tactics") or [{}])[0].get("name", "未知") if item.get("tactics") else "未知"
            digest.append(
                {
                    "rally_index": item.get("rally_index"),
                    "event": item.get("physics", {}).get("event", "未知"),
                    "verdict": item.get("auto_result", "UNKNOWN"),
                    "top_tactic": tactic,
                    "pressure": round(float(item.get("physics", {}).get("pressure_index", 0.0) or 0.0), 3),
                }
            )
        return digest

    def _storyline_cards(self, opening_phase: Dict, turning_points: List[Dict], adaptation_cycles: List[Dict], closing_state: Dict) -> List[Dict]:
        cards = []
        if opening_phase:
            cards.append({"stage": "opening", "title": opening_phase.get("headline", "开局"), "body": opening_phase.get("summary", "")})
        for turning_point in turning_points[:2]:
            cards.append({"stage": "turn", "title": f"回合 {turning_point.get('rally_index')}", "body": turning_point.get("trigger", "")})
        for cycle in adaptation_cycles[:2]:
            cards.append({"stage": "adapt", "title": cycle.get("to", "适应"), "body": cycle.get("summary", "")})
        if closing_state:
            cards.append({"stage": "closing", "title": "收官状态", "body": closing_state.get("summary", "")})
        return cards

    def _summary(self, opening_phase: Dict, turning_points: List[Dict], closing_state: Dict) -> str:
        opening_text = opening_phase.get("summary", "开局阶段信息不可用。")
        turn_text = f"主要转折点出现在第 {turning_points[0].get('rally_index', '?')} 回合附近。" if turning_points else "当前时间线未检测到明显转折点。"
        closing_text = closing_state.get("summary", "收官状态信息不可用。")
        return f"{opening_text} {turn_text} {closing_text}"

    def _turning_trigger(self, prev_result: str, curr_result: str, prev_tactic: str, curr_tactic: str, current_pressure: float, threshold: float) -> str:
        if curr_result != prev_result:
            return f"结果从 {_RESULT_MAP.get(prev_result, prev_result)} 翻转为 {_RESULT_MAP.get(curr_result, curr_result)}，比赛势头发生变化。"
        if curr_tactic != prev_tactic:
            return f"战术锚点从 {prev_tactic} 转变为 {curr_tactic}。"
        if current_pressure >= threshold:
            return f"压力飙升至 {current_pressure:.2f}，形成高杠杆回合。"
        return "该回合改变了比赛节奏，但没有单一主导触发因素。"
