from __future__ import annotations

from typing import Dict, List

import numpy as np

from core.utils.label_zh import zh_phase, zh_style, zh_policy, zh_strategy


class TacticEvolutionReplayer:
    def build_candidate_replays(self, candidates: List[Dict], context: Dict | None = None, scenario_summary: Dict | None = None) -> List[Dict]:
        context = context or {}
        scenario_summary = scenario_summary or {}
        if not candidates:
            return []

        enriched = []
        frontier_summary = self._frontier_summary(candidates, scenario_summary)
        for index, candidate in enumerate(candidates, start=1):
            replay = self._candidate_replay(index, candidate, context, scenario_summary, frontier_summary)
            enriched.append(
                {
                    **candidate,
                    "evolution_replay": replay,
                    "frontier_hint": replay.get("frontier_hint", candidate.get("frontier_hint", "")),
                }
            )
        return enriched

    def summarize_update(self, tactic_id: str, reward: float, update_payload: Dict | None = None, context: Dict | None = None, tactic_name: str | None = None) -> Dict:
        update_payload = update_payload or {}
        context = context or {}
        scheduler_profile = update_payload.get("scheduler_profile", {}) or {}
        scenario_summary = update_payload.get("scenario_summary", {}) or {}
        weighted_increment = float(update_payload.get("weighted_increment", 0.0) or 0.0)
        certainty_weight = float(update_payload.get("certainty_weight", 0.5) or 0.5)
        adaptation_level = update_payload.get("adaptation_level", "moderate")
        policy_mode = scheduler_profile.get("memory_stability", 0.5)
        direction = "reinforce" if reward >= 0 else "cooldown"
        tactic_label = tactic_name or tactic_id

        replay_score = float(np.clip(
            0.32 * certainty_weight
            + 0.24 * min(abs(reward) / 10.0, 1.0)
            + 0.22 * float(scheduler_profile.get("learning_rate_scale", 1.0) or 1.0)
            + 0.22 * float(scenario_summary.get("familiarity", 0.0) or 0.0),
            0.0,
            1.25,
        ))
        direction_label = {"reinforce": "强化", "cooldown": "冷却"}.get(direction, direction)
        level_label = {"strong": "强", "moderate": "中", "conservative": "保守"}.get(adaptation_level, adaptation_level)
        summary = (
            f"{tactic_label} 进入{direction_label}周期，加权增量 {weighted_increment:.2f}，"
            f"确定性权重 {certainty_weight:.2f}，适应级别{level_label}。"
        )

        return {
            "tactic_id": tactic_id,
            "tactic_name": tactic_label,
            "direction": direction,
            "reward": round(float(reward or 0.0), 3),
            "replay_score": round(replay_score, 3),
            "adaptation_level": adaptation_level,
            "stability_reference": round(float(policy_mode or 0.0), 3),
            "scenario_familiarity": round(float(scenario_summary.get("familiarity", 0.0) or 0.0), 3),
            "upgrade_path": self._update_upgrade_path(context, update_payload),
            "summary": summary,
        }

    def _candidate_replay(
        self,
        rank: int,
        candidate: Dict,
        context: Dict,
        scenario_summary: Dict,
        frontier_summary: Dict,
    ) -> Dict:
        metadata = candidate.get("metadata", {}) or {}
        policy_mode = (candidate.get("scheduler_profile", {}) or {}).get("policy_mode", "balanced")
        risk_level = metadata.get("risk_level", "medium")
        style_family = metadata.get("style_family", "balanced")
        score = float(candidate.get("rerank_score", candidate.get("score", 0.0)) or 0.0)
        familiarity = float(scenario_summary.get("familiarity", 0.0) or 0.0)
        continuity = float(candidate.get("continuity_score", 0.5) or 0.5)
        coverage = float(candidate.get("coverage_score", 0.5) or 0.5)
        replay_score = float(np.clip(0.42 * score + 0.26 * continuity + 0.18 * coverage + 0.14 * (1.0 - 0.45 * familiarity), 0.0, 1.45))
        development_stage = self._development_stage(rank, policy_mode, familiarity, replay_score)
        training_block = self._training_block(context, risk_level, style_family)
        frontier_hint = self._frontier_hint(rank, development_stage, frontier_summary, risk_level)

        return {
            "development_stage": development_stage,
            "policy_mode": policy_mode,
            "replay_score": round(replay_score, 3),
            "risk_axis": risk_level,
            "training_block": training_block,
            "why_now": self._why_now(candidate, context, familiarity),
            "upgrade_path": self._candidate_upgrade_path(candidate, context, policy_mode),
            "frontier_hint": frontier_hint,
        }

    def _frontier_summary(self, candidates: List[Dict], scenario_summary: Dict) -> Dict:
        if not candidates:
            return {"frontier_shape": "empty", "stability_gap": 0.0}
        top_score = float(candidates[0].get("rerank_score", candidates[0].get("score", 0.0)) or 0.0)
        third_score = float(candidates[min(2, len(candidates) - 1)].get("rerank_score", candidates[min(2, len(candidates) - 1)].get("score", 0.0)) or 0.0)
        stability_gap = float(np.clip(top_score - third_score, 0.0, 1.0))
        familiarity = float(scenario_summary.get("familiarity", 0.0) or 0.0)
        if stability_gap >= 0.28:
            frontier_shape = "sharp"
        elif familiarity < 0.3:
            frontier_shape = "open"
        else:
            frontier_shape = "layered"
        return {
            "frontier_shape": frontier_shape,
            "stability_gap": round(stability_gap, 3),
        }

    def _development_stage(self, rank: int, policy_mode: str, familiarity: float, replay_score: float) -> str:
        if rank == 1 and replay_score >= 0.95 and policy_mode == "exploit":
            return "weaponize"
        if familiarity < 0.28:
            return "probe"
        if replay_score >= 0.78:
            return "refine"
        return "stabilize"

    def _training_block(self, context: Dict, risk_level: str, style_family: str) -> str:
        attack_phase = context.get("attack_phase", "neutral")
        if attack_phase == "under_pressure":
            return "压力吸收 + 反击释放"
        if risk_level == "high":
            return f"提前为 {zh_style(style_family)} 投入做准备"
        if attack_phase == "advantage":
            return "在第一个干净窗口结束回合"
        return "节奏控制和结构保持"

    def _why_now(self, candidate: Dict, context: Dict, familiarity: float) -> str:
        tactic_name = candidate.get("name", "该战术")
        phase = zh_phase(context.get("attack_phase", "neutral"))
        score = float(candidate.get("rerank_score", candidate.get("score", 0.0)) or 0.0)
        if familiarity < 0.25:
            return f"{tactic_name} 值得现在探索，因为 {phase} 分支仍未充分学习，当前得分 {score:.2f}。"
        return f"{tactic_name} 现在很合适，因为它在 {phase} 交换中保持了 {score:.2f} 的强排名值。"

    def _candidate_upgrade_path(self, candidate: Dict, context: Dict, policy_mode: str) -> List[str]:
        phase = zh_phase(context.get("attack_phase", "neutral"))
        tactic_name = candidate.get("name", "该战术")
        steps = [
            f"从 {phase} 情景演练 {tactic_name} 的进入方式。",
            "跟踪第一次进攻触球是创造了空间还是引发了混乱。",
        ]
        if policy_mode == "explore":
            steps.append("在确定固定偏好之前保持广泛的样本量。")
        else:
            steps.append("强化最可重复的变体，剪除噪声分支。")
        return steps

    def _frontier_hint(self, rank: int, development_stage: str, frontier_summary: Dict, risk_level: str) -> str:
        frontier_shape = frontier_summary.get("frontier_shape", "layered")
        shape_label = {"sharp": "尖锐", "open": "开放", "layered": "分层"}.get(frontier_shape, frontier_shape)
        if development_stage == "weaponize":
            return f"前沿为{shape_label}；该分支可以固化为主要得分模式。"
        if risk_level == "high":
            return f"前沿为{shape_label}；将该分支作为选择性武器而非默认习惯。"
        if rank > 1:
            return f"前沿为{shape_label}；保持该分支作为变化的备用通道。"
        return f"前沿为{shape_label}；在横向扩展前继续精炼该分支。"

    def _update_upgrade_path(self, context: Dict, update_payload: Dict) -> List[str]:
        reason = update_payload.get("policy_update_reason", "")
        strategy_tag = update_payload.get("strategy_tag", "adapt")
        phase = zh_phase(context.get("attack_phase", "neutral"))
        return [
            f"将 {zh_strategy(strategy_tag)} 作为 {phase} 回合的下一个调整框架。",
            reason or "本次更新后仅保留战术的稳定分支。",
            "在接下来几个回合后重新检查该战术是否仍然适合相同的场地上下文。",
        ]
