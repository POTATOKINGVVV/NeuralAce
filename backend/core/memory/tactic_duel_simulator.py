from __future__ import annotations

from collections import Counter
from typing import Dict, List

import numpy as np

from core.utils.label_zh import zh_phase


COUNTER_FAMILY_MAP = {
    "absorb-and-redirect": ["compression-attack", "front-court-trap"],
    "reset-and-rebuild": ["interception", "compression-attack"],
    "front-court-trap": ["reset-and-rebuild", "deception"],
    "attritional-pressure": ["deception", "interception"],
    "compression-attack": ["absorb-and-redirect", "managed-pressure"],
    "deception": ["front-court-trap", "reset-and-rebuild"],
    "interception": ["absorb-and-redirect", "managed-pressure"],
    "managed-pressure": ["interception", "front-court-trap"],
}


class TacticDuelSimulator:
    def __init__(self, tactic_seeds: List[Dict]):
        self.tactic_seeds = tactic_seeds
        self.seed_by_family = self._index_by_family(tactic_seeds)

    def simulate(self, tactics: List[Dict], state: Dict, sequence_context: Dict | None = None) -> Dict:
        sequence_context = sequence_context or {}
        if not tactics:
            return self._empty_projection()

        primary = tactics[0]
        metadata = primary.get("metadata", {}) or {}
        primary_family = metadata.get("style_family", "balanced")
        primary_name = primary.get("name", "中性重置")
        primary_phase = state.get("attack_phase", "neutral")
        likely_response = self._likely_response(primary_family, primary_phase, sequence_context)
        counter_tactics = self._counter_tactics(primary, state, sequence_context)
        duel_risk = self._duel_risk(primary, state, sequence_context)
        duel_risk_label = self._risk_label(duel_risk)
        counter_window = self._counter_window(state, metadata)
        exchange_script = self._exchange_script(primary_name, likely_response, counter_tactics, primary_phase)
        duel_explanation = self._duel_explanation(primary_name, likely_response, duel_risk_label, sequence_context)

        return {
            "primary_plan": primary_name,
            "likely_response": likely_response,
            "counter_window": counter_window,
            "duel_risk": round(duel_risk, 3),
            "duel_risk_label": duel_risk_label,
            "counter_tactics": counter_tactics,
            "exchange_script": exchange_script,
            "duel_explanation": duel_explanation,
            "pressure_gate": self._pressure_gate(state, duel_risk),
        }

    def summarize_matchup(self, timeline: List[Dict], sequence_context: Dict | None = None) -> Dict:
        sequence_context = sequence_context or {}
        if not timeline:
            return {
                "dominant_duel": "不可用",
                "recurring_counters": [],
                "duel_risk_profile": {},
                "duel_cards": [],
            }

        duel_items = [((item.get("diagnostics", {}) or {}).get("duel_projection", {}) or {}) for item in timeline]
        duel_items = [item for item in duel_items if item]
        if not duel_items:
            return {
                "dominant_duel": "不可用",
                "recurring_counters": [],
                "duel_risk_profile": {},
                "duel_cards": [],
            }

        pair_counter = Counter(f"{item.get('primary_plan', '未知')} -> {item.get('likely_response', '未知')}" for item in duel_items)
        response_counter = Counter(item.get("likely_response", "未知") for item in duel_items)
        duel_risks = [float(item.get("duel_risk", 0.0) or 0.0) for item in duel_items]
        dominant_duel = pair_counter.most_common(1)[0][0] if pair_counter else "不可用"
        recurring_counters = [{"name": name, "count": count} for name, count in response_counter.most_common(3)]
        duel_cards = []
        for item in duel_items[:3]:
            duel_cards.append(
                {
                    "title": item.get("primary_plan", "未知"),
                    "body": item.get("duel_explanation", ""),
                    "risk": item.get("duel_risk_label", "medium"),
                }
            )

        return {
            "dominant_duel": dominant_duel,
            "recurring_counters": recurring_counters,
            "duel_risk_profile": {
                "mean_duel_risk": round(float(np.mean(duel_risks)) if duel_risks else 0.0, 3),
                "max_duel_risk": round(float(np.max(duel_risks)) if duel_risks else 0.0, 3),
                "pressure_script": (sequence_context.get("pressure_swing", {}) or {}).get("label", "steady-pressure"),
            },
            "duel_cards": duel_cards,
        }

    def _index_by_family(self, tactic_seeds: List[Dict]) -> Dict[str, List[Dict]]:
        indexed: Dict[str, List[Dict]] = {}
        for seed in tactic_seeds:
            indexed.setdefault(seed.get("style_family", "balanced"), []).append(seed)
        return indexed

    def _likely_response(self, primary_family: str, primary_phase: str, sequence_context: Dict) -> str:
        pressure_label = (sequence_context.get("pressure_swing", {}) or {}).get("label", "steady-pressure")
        if primary_phase == "advantage":
            return "对手可能会紧凑防守，寻找直线重置的窗口。"
        if primary_phase == "under_pressure":
            return "对手可能会加速下一个中性球，压缩你的恢复时间。"
        if pressure_label == "rising-pressure":
            return "对手可能会缩短交换并攻击第一个松动的回球。"
        if primary_family == "deception":
            return "对手可能会稳住重心，延迟对第一个假动作的反应。"
        return "对手可能会用稳定球应对，等待你过度投入的机会。"

    def _counter_tactics(self, primary: Dict, state: Dict, sequence_context: Dict) -> List[Dict]:
        metadata = primary.get("metadata", {}) or {}
        primary_family = metadata.get("style_family", "balanced")
        candidate_families = COUNTER_FAMILY_MAP.get(primary_family, ["reset-and-rebuild", "absorb-and-redirect"])
        counters = []
        for family in candidate_families:
            for seed in self.seed_by_family.get(family, [])[:2]:
                fit_score = self._counter_fit(seed, state, sequence_context)
                counters.append(
                    {
                        "name": seed.get("name", "未知"),
                        "family": family,
                        "fit_score": round(fit_score, 3),
                        "reason": self._counter_reason(seed, state),
                    }
                )
        counters.sort(key=lambda item: item.get("fit_score", 0.0), reverse=True)
        return counters[:3]

    def _counter_fit(self, seed: Dict, state: Dict, sequence_context: Dict) -> float:
        phase = state.get("attack_phase", "neutral")
        event = state.get("event", "未知")
        preferred_style = sequence_context.get("preferred_style_family", "balanced")
        phase_fit = 1.0 if seed.get("phase_preference") == phase else 0.62
        event_fit = 1.0 if event in seed.get("applicable_events", []) else 0.54
        style_bonus = 0.12 if seed.get("style_family") == preferred_style else 0.0
        pressure_penalty = 0.12 if phase == "under_pressure" and seed.get("risk_level") == "high" else 0.0
        return float(np.clip(0.46 * phase_fit + 0.42 * event_fit + style_bonus - pressure_penalty, 0.0, 1.0))

    def _counter_reason(self, seed: Dict, state: Dict) -> str:
        return (
            f"{seed.get('name', '该战术')} 适合 {zh_phase(state.get('attack_phase', 'neutral'))} 交换，"
            f"可以应对 {state.get('event', '当前回合')} 模式而不完全镜像对方。"
        )

    def _duel_risk(self, primary: Dict, state: Dict, sequence_context: Dict) -> float:
        metadata = primary.get("metadata", {}) or {}
        risk_level = metadata.get("risk_level", "medium")
        base = {"low": 0.28, "medium": 0.5, "high": 0.72}.get(risk_level, 0.5)
        pressure = float(state.get("pressure_index", 0.5) or 0.5)
        volatility = float((sequence_context.get("pressure_swing", {}) or {}).get("volatility", 0.0) or 0.0)
        adaptation_score = float(sequence_context.get("adaptation_score", 0.0) or 0.0)
        return float(np.clip(base + 0.22 * pressure + 0.12 * volatility + 0.08 * adaptation_score, 0.0, 1.0))

    def _risk_label(self, duel_risk: float) -> str:
        if duel_risk >= 0.74:
            return "high"
        if duel_risk >= 0.48:
            return "medium"
        return "low"

    def _counter_window(self, state: Dict, metadata: Dict) -> str:
        phase = state.get("attack_phase", "neutral")
        tempo = state.get("tempo_profile", "medium")
        if phase == "advantage":
            return "finish-window"
        if tempo == "fast":
            return "first-two-shots"
        if metadata.get("risk_level") == "high":
            return "single-clean-chance"
        return "extended-exchange"

    def _exchange_script(self, primary_name: str, likely_response: str, counter_tactics: List[Dict], primary_phase: str) -> List[str]:
        script = [f"从 {zh_phase(primary_phase)} 位置以 {primary_name} 开局。", likely_response]
        if counter_tactics:
            script.append(f"如果交换转向，最佳反击路线是 {counter_tactics[0].get('name', '未知')}。")
        return script

    def _duel_explanation(self, primary_name: str, likely_response: str, duel_risk_label: str, sequence_context: Dict) -> str:
        risk_map = {"high": "高", "medium": "中", "low": "低"}
        risk_cn = risk_map.get(duel_risk_label, "中")
        memory_summary = sequence_context.get("memory_summary", "序列记忆有限。")
        return f"{primary_name} 进入{risk_cn}风险对抗。{likely_response} 序列记忆补充：{memory_summary}"

    def _pressure_gate(self, state: Dict, duel_risk: float) -> str:
        pressure = float(state.get("pressure_index", 0.5) or 0.5)
        if duel_risk >= 0.72 or pressure >= 0.74:
            return "仅在提前准备充分时才应进入该对抗。"
        if duel_risk >= 0.48:
            return "仅在第一拍接触后重心仍稳定时才应进入对抗。"
        return "对抗足够稳定，可以在下一次交换中继续施压。"

    def _empty_projection(self) -> Dict:
        return {
            "primary_plan": "中性重置",
            "likely_response": "暂无对抗推演。",
            "counter_window": "unknown",
            "duel_risk": 0.0,
            "duel_risk_label": "low",
            "counter_tactics": [],
            "exchange_script": [],
            "duel_explanation": "没有可用战术，无法生成对抗推演。",
            "pressure_gate": "先稳定回合节奏。",
        }
