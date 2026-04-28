from __future__ import annotations

from collections import Counter
from typing import Dict, List

from core.utils.label_zh import zh, zh_phase


class TrainingPrescriptor:
    def build_rally_plan(self, state: Dict, tactics: List[Dict], diagnostics: Dict) -> Dict:
        top_tactic = tactics[0] if tactics else {}
        confidence_report = diagnostics.get("confidence_report", {}) or {}
        referee_audit = diagnostics.get("referee_audit", {}) or {}
        pressure_index = float(state.get("pressure_index", 0.5) or 0.5)
        confidence = float(confidence_report.get("calibrated_confidence", 0.5) or 0.5)
        risk_note = top_tactic.get("risk_note", "先稳住结构再发力。")

        theme = self._theme(state, top_tactic, referee_audit)
        micro_goal = self._micro_goal(state, top_tactic, pressure_index)
        guardrail = referee_audit.get("recommended_action") or risk_note
        blocks = [
            self._block("影子演练", 8, "low", f"在触球前先建立 {theme.lower()} 的进入模式。"),
            self._block("限制性喊球", 12, "medium", micro_goal),
            self._block("压力收尾", 10, "high" if pressure_index >= 0.62 else "medium", risk_note),
        ]

        return {
            "theme": theme,
            "priority": self._priority(confidence, pressure_index, referee_audit.get("audit_level", "watch")),
            "micro_goal": micro_goal,
            "guardrail": guardrail,
            "blocks": blocks,
        }

    def build_match_plan(self, intelligence: Dict, timeline: List[Dict]) -> Dict:
        attack_phases = [
            (item.get("physics", {}) or {}).get("attack_phase", "neutral")
            for item in timeline
            if item.get("physics")
        ]
        top_phases = Counter(attack_phases).most_common(2)
        recommended_focus = intelligence.get("recommended_focus", []) or []
        blocks = []
        for index, focus in enumerate(recommended_focus[:3], start=1):
            blocks.append(
                {
                    "label": f"比赛训练 {index}",
                    "goal": zh(focus),
                    "duration_min": 14 if index == 1 else 10,
                }
            )

        return {
            "match_theme": intelligence.get("tactical_identity", "自适应"),
            "phase_distribution": [{"phase": phase, "count": count} for phase, count in top_phases],
            "focus_queue": recommended_focus[:3],
            "blocks": blocks,
        }

    def _theme(self, state: Dict, top_tactic: Dict, referee_audit: Dict) -> str:
        attack_phase = zh_phase(state.get("attack_phase", "neutral"))
        tactic_name = top_tactic.get("name") or state.get("event", "回合")
        audit_level = referee_audit.get("audit_level", "watch")
        if audit_level == "escalate":
            return f"稳定 {attack_phase} 决策质量"
        return f"{attack_phase} 围绕 {tactic_name} 执行"

    def _micro_goal(self, state: Dict, top_tactic: Dict, pressure_index: float) -> str:
        recommended_action = top_tactic.get("recommended_action") or "先稳住重心再准备下一拍。"
        if pressure_index >= 0.65:
            return f"先保持结构，然后执行：{recommended_action}"
        return f"重复第一个干净的提示并完成：{recommended_action}"

    def _priority(self, confidence: float, pressure_index: float, audit_level: str) -> str:
        if audit_level == "escalate" or confidence < 0.42:
            return "stability-first"
        if pressure_index >= 0.66:
            return "pressure-management"
        return "pattern-reinforcement"

    def _block(self, label: str, duration_min: int, intensity: str, goal: str) -> Dict:
        return {
            "label": label,
            "duration_min": duration_min,
            "intensity": intensity,
            "goal": goal,
        }
