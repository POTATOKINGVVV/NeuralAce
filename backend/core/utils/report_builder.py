from __future__ import annotations

from collections import Counter
from typing import Dict, List


class ReportBuilder:
    def build_rally_report(self, state: Dict, summary: Dict, diagnostics: Dict, tactics: List[Dict], training_plan: Dict | None = None) -> Dict:
        top_tactic = tactics[0] if tactics else {}
        confidence_report = diagnostics.get("confidence_report", {})
        tracker_diagnostics = diagnostics.get("tracker_diagnostics", {})
        referee_audit = diagnostics.get("referee_audit", {})
        sequence_context = diagnostics.get("sequence_context", {})
        duel_projection = diagnostics.get("duel_projection", {})
        return {
            "headline": summary.get("headline", "回合已分析"),
            "verdict": summary.get("verdict", "UNKNOWN"),
            "top_tactic": top_tactic.get("name", "中性重置") if top_tactic else "中性重置",
            "technical_snapshot": {
                "event": state.get("event", "未知"),
                "pressure_index": state.get("pressure_index", 0.0),
                "attack_phase": state.get("attack_phase", "neutral"),
                "tempo_profile": state.get("tempo_profile", "medium"),
            },
            "confidence_snapshot": confidence_report,
            "tracking_snapshot": {
                "signal_integrity": tracker_diagnostics.get("signal_integrity", 0.0),
                "repaired_points": tracker_diagnostics.get("repaired_points", 0),
                "spike_count": tracker_diagnostics.get("spike_count", 0),
            },
            "referee_snapshot": referee_audit,
            "sequence_snapshot": {
                "memory_summary": sequence_context.get("memory_summary", ""),
                "sequence_tags": sequence_context.get("sequence_tags", []),
                "streak_context": sequence_context.get("streak_context", {}),
            },
            "duel_snapshot": duel_projection,
            "tactic_snapshot": {
                "why_this_tactic": top_tactic.get("why_this_tactic", ""),
                "risk_note": top_tactic.get("risk_note", ""),
                "rank_reason": top_tactic.get("rank_reason", ""),
                "frontier_hint": top_tactic.get("frontier_hint", ""),
                "evolution_replay": top_tactic.get("evolution_replay", {}),
            },
            "training_plan": training_plan or {},
            "coach_takeaway": summary.get("key_takeaway", "专注下一次交换的稳定执行。"),
        }

    def build_match_report(self, intelligence: Dict, timeline: List[Dict], training_plan: Dict | None = None, sequence_context: Dict | None = None, duel_summary: Dict | None = None, replay_story: Dict | None = None) -> Dict:
        sequence_context = sequence_context or {}
        duel_summary = duel_summary or {}
        replay_story = replay_story or {}
        audit_levels = [((item.get("diagnostics", {}) or {}).get("referee_audit", {}) or {}).get("audit_level", "watch") for item in timeline]
        audit_distribution = Counter(audit_levels)
        return {
            "headline": self._headline(intelligence),
            "dominant_pattern": intelligence.get("dominant_pattern", "未知"),
            "tactical_identity": intelligence.get("tactical_identity", "自适应"),
            "momentum_state": intelligence.get("momentum_state", "neutral"),
            "recommended_focus": intelligence.get("recommended_focus", []),
            "rally_count": len(timeline),
            "audit_distribution": dict(audit_distribution),
            "sequence_memory": sequence_context,
            "duel_summary": duel_summary,
            "replay_story": replay_story,
            "training_plan": training_plan or {},
            "narrative": self._narrative(intelligence),
        }

    def _headline(self, intelligence: Dict) -> str:
        momentum = intelligence.get("momentum_state", "neutral")
        if momentum == "surging":
            return "整场比赛势头偏向你这一方。"
        if momentum == "under-pressure":
            return "比赛趋势偏向被动应对。"
        return "整场比赛呈现均衡的战术节奏。"

    def _narrative(self, intelligence: Dict) -> str:
        dominant = intelligence.get("dominant_pattern", "未知")
        identity = intelligence.get("tactical_identity", "自适应")
        trend = intelligence.get("confidence_trend", "flat")
        trend_label = {"rising": "上升", "falling": "下降", "flat": "平稳"}.get(trend, "平稳")
        focus = "、".join(intelligence.get("recommended_focus", [])[:2]) or "保持均衡决策"
        return f"整场比赛主要围绕 {dominant} 模式展开，{identity} 是最突出的战术身份。置信度趋势保持{trend_label}，下一步训练应优先关注{focus}。"
