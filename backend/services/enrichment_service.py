from typing import Dict, List

from core.utils.label_zh import zh_phase, zh_court, zh_style


def _confidence_label(score: float, expected_win_rate: float, context_score: float = 0.5, risk_penalty: float = 0.0) -> str:
    composite = 0.45 * score + 0.3 * (expected_win_rate / 100.0) + 0.25 * context_score - 0.15 * risk_penalty
    if composite >= 0.76 or expected_win_rate >= 74:
        return "high"
    if composite <= 0.5 or expected_win_rate <= 45:
        return "low"
    return "medium"


def _format_action_from_content(content: str) -> str:
    if not content:
        return "重置并准备下一次交换。"
    for sep in ["。", "."]:
        if sep in content:
            sentence = content.split(sep)[0].strip()
            return sentence if sentence.endswith(("。", ".")) else f"{sentence}。"
    return content.strip() if content.strip().endswith(("。", ".")) else f"{content.strip()}。"


def _build_why_this_tactic(name: str, event_name: str, speed: float, expected_win_rate: float, confidence_label: str, rank: int, attack_phase: str, court_context: str, style_family: str) -> str:
    rank_context = "最优匹配" if rank == 1 else f"第 {rank} 优先方案"
    confidence_context = {"high": "历史数据支撑充分", "medium": "置信度均衡", "low": "作为探索性备选"}.get(confidence_label, "置信度均衡")
    return (
        f"{name} 是该 {event_name} 模式在 {speed:.1f} km/h 下的{rank_context}，"
        f"适配 {attack_phase} 阶段的 {court_context} 区域，通过 {style_family} 风格应对，"
        f"预期胜率 {expected_win_rate:.1f}%，{confidence_context}。"
    )


def _build_risk_note(event_name: str, speed: float, confidence_label: str, expected_win_rate: float, risk_level: str, attack_phase: str) -> str:
    if risk_level == "high" and attack_phase == "under_pressure":
        return "这是高投入的压力应对方案，仅在重心稳固时才应采用。"
    if confidence_label == "low":
        return "该方案属于探索性选择，如果对手提前读懂意图，需要快速还原。"
    if speed >= 200:
        return f"该 {event_name} 情境下节奏非常快，时机和击球质量至关重要。"
    if expected_win_rate < 55:
        return "战术优势不明显，执行质量比战术模式本身更重要。"
    return "该选择比较稳定，但仍需提前准备和干净的步伐衔接。"


def enrich_tactics(state: Dict, tactics: List[Dict]) -> List[Dict]:
    enriched = []
    event_name = state.get("event", "回合")
    speed = state.get("max_speed_kmh", 0.0)
    attack_phase = state.get("attack_phase", "neutral")
    court_context = state.get("court_context", "unknown")

    for index, tactic in enumerate(tactics, start=1):
        expected_win_rate = float(tactic.get("expected_win_rate", 50.0))
        ranking_score = float(tactic.get("rerank_score", tactic.get("score", 0.0)) or 0.0)
        context_score = float(tactic.get("context_score", 0.5))
        risk_penalty = float(tactic.get("risk_penalty", 0.0))
        metadata = tactic.get("metadata", {})
        name = tactic.get("name") or tactic.get("content") or f"\u6218\u672f {index}"
        recommended_action = _format_action_from_content(tactic.get("content", name))
        confidence_label = _confidence_label(ranking_score, expected_win_rate, context_score, risk_penalty)
        style_family = metadata.get("style_family", "balanced")
        risk_level = metadata.get("risk_level", "medium")

        rank_hint = "首选推荐" if index == 1 else f"第 {index} 优先方案"
        reason = f"{name} 是{rank_hint}，因为它匹配 {event_name.lower()} 场景（{speed:.1f} km/h），符合 {zh_phase(attack_phase)} 阶段，预期胜率 {expected_win_rate:.1f}%。"
        why_this_tactic = _build_why_this_tactic(name, event_name.lower(), speed, expected_win_rate, confidence_label, index, zh_phase(attack_phase), zh_court(court_context), zh_style(style_family))
        risk_note = _build_risk_note(event_name, speed, confidence_label, expected_win_rate, risk_level, attack_phase)

        enriched.append(
            {
                **tactic,
                "name": name,
                "recommended_action": recommended_action,
                "confidence_label": confidence_label,
                "reason": reason,
                "why_this_tactic": why_this_tactic,
                "risk_note": risk_note,
                "fit_breakdown": tactic.get("fit_breakdown", {}),
                "selection_profile": tactic.get("selection_profile", {}),
                "scenario_summary": tactic.get("scenario_summary", {}),
                "related_tactics": tactic.get("related_tactics", []),
                "transition_family": tactic.get("transition_family", "isolated"),
                "rerank_score": tactic.get("rerank_score", tactic.get("score", 0.0)),
                "continuity_score": tactic.get("continuity_score", 0.0),
                "coverage_score": tactic.get("coverage_score", 0.0),
                "volatility_guard": tactic.get("volatility_guard", 0.0),
                "novelty_bonus": tactic.get("novelty_bonus", 0.0),
                "rank_reason": tactic.get("rank_reason", ""),
                "frontier_hint": tactic.get("frontier_hint", ""),
                "evolution_replay": tactic.get("evolution_replay", {}),
            }
        )

    return enriched


def normalize_advice_payload(raw_advice, tactics: List[Dict], state: Dict) -> Dict:
    if isinstance(raw_advice, dict):
        text = raw_advice.get("text") or "保持平衡，提前准备。"
        headline = raw_advice.get("headline") or "保持冷静"
        focus = raw_advice.get("focus") or "恢复调整"
        next_step = raw_advice.get("next_step") or "准备下一拍击球。"
        confidence_label = raw_advice.get("confidence_label") or (tactics[0].get("confidence_label", "medium") if tactics else "medium")
        source = raw_advice.get("source") or "llm"
    else:
        text = str(raw_advice or "保持平衡，提前准备。")
        top_tactic = tactics[0]["name"] if tactics else state.get("event", "回合")
        headline = f"执行 {top_tactic}"
        focus = zh_phase(state.get("attack_phase", "落点控制"))
        next_step = tactics[0].get("recommended_action", "准备下一拍击球。") if tactics else "准备下一拍击球。"
        confidence_label = tactics[0].get("confidence_label", "medium") if tactics else "medium"
        source = "fallback"

    return {
        "text": text,
        "headline": headline,
        "focus": focus,
        "next_step": next_step,
        "confidence_label": confidence_label,
        "source": source,
    }


def build_summary_payload(state: Dict, advice: Dict, tactics: List[Dict], auto_result: str) -> Dict:
    top_tactic = tactics[0]["name"] if tactics else "中性重置"
    confidence_label = advice.get("confidence_label", tactics[0].get("confidence_label", "medium") if tactics else "medium")
    verdict = auto_result or "UNKNOWN"
    attack_phase = zh_phase(state.get("attack_phase", "neutral"))
    shot_shape = zh_style(state.get("shot_shape", "均衡回合"))

    if verdict == "WIN":
        headline = "检测到得分模式"
    elif verdict == "LOSS":
        headline = "压力应对有待加强"
    else:
        headline = "回合模式已捕捉"

    key_takeaway = f"主要战术方向：{top_tactic}。当前阶段为 {attack_phase}，击球形态为 {shot_shape}，下一步应专注于{advice.get('focus', '落点控制').lower()}。"
    return {"headline": headline, "verdict": verdict, "confidence_label": confidence_label, "key_takeaway": key_takeaway}


def build_diagnostics_payload(warnings: List[str], pipeline_status: Dict[str, str], motion_feedback: str, trajectory_points: int, tactics: List[Dict], state: Dict = None, tracker_diagnostics: Dict = None, motion_profile: Dict = None, rally_quality: Dict = None, confidence_report: Dict = None, referee_audit: Dict = None, sequence_context: Dict = None, duel_projection: Dict = None) -> Dict:
    state = state or {}
    tracker_diagnostics = tracker_diagnostics or {}
    motion_profile = motion_profile or {}
    rally_quality = rally_quality or {}
    confidence_report = confidence_report or {}
    referee_audit = referee_audit or {}
    sequence_context = sequence_context or {}
    duel_projection = duel_projection or {}

    if warnings:
        analysis_quality = "degraded" if len(warnings) > 1 else "limited"
    elif trajectory_points < 8:
        analysis_quality = "low"
    elif rally_quality.get("overall_quality", 0.0) >= 0.76:
        analysis_quality = "high"
    else:
        analysis_quality = "medium"

    retrieval_summary = {}
    if tactics:
        top = tactics[0]
        metadata = top.get("metadata", {})
        retrieval_summary = {
            "selected_tactic": top.get("name", "未知"),
            "score": round(float(top.get("score", 0.0)), 3),
            "rerank_score": round(float(top.get("rerank_score", top.get("score", 0.0)) or 0.0), 3),
            "expected_win_rate": round(float(top.get("expected_win_rate", 50.0)), 2),
            "style_family": metadata.get("style_family", "balanced"),
            "phase_preference": metadata.get("phase_preference", "neutral"),
            "tempo_band": metadata.get("tempo_band", "medium"),
            "risk_level": metadata.get("risk_level", "medium"),
            "fit_breakdown": top.get("fit_breakdown", {}),
            "scenario_summary": top.get("scenario_summary", {}),
            "transition_family": top.get("transition_family", "isolated"),
            "rank_reason": top.get("rank_reason", ""),
            "frontier_hint": top.get("frontier_hint", ""),
            "development_stage": (top.get("evolution_replay", {}) or {}).get("development_stage", "stabilize"),
        }

    combined_warnings = list(warnings)
    combined_warnings.extend(rally_quality.get("warnings", []))

    return {
        "warnings": combined_warnings,
        "pipeline": pipeline_status,
        "motion_feedback": motion_feedback,
        "trajectory_points": trajectory_points,
        "analysis_quality": analysis_quality,
        "retrieval_summary": retrieval_summary,
        "physics_profile": {
            "attack_phase": state.get("attack_phase", "neutral"),
            "tempo_profile": state.get("tempo_profile", "medium"),
            "shot_shape": state.get("shot_shape", "balanced-rally"),
            "pressure_index": state.get("pressure_index", 0.0),
        },
        "tracker_diagnostics": tracker_diagnostics,
        "motion_profile": motion_profile,
        "rally_quality": rally_quality,
        "confidence_report": confidence_report,
        "referee_audit": referee_audit,
        "sequence_context": sequence_context,
        "duel_projection": duel_projection,
    }


def make_empty_rally_response(match_type: str, warning: str) -> Dict:
    advice = {
        "text": "该片段无法可靠分析。请尝试更清晰的回合角度或稍长的片段。",
        "headline": "分析未完成",
        "focus": "采集质量",
        "next_step": "上传更稳定的回合片段，确保完整的球路可见。",
        "confidence_label": "low",
        "source": "fallback",
    }
    summary = {
        "headline": "回合信号不足",
        "verdict": "UNKNOWN",
        "confidence_label": "low",
        "key_takeaway": "当前片段的可靠信号不足，无法进行战术分析。",
    }
    diagnostics = {
        "warnings": [warning],
        "pipeline": {"tracking": "failed", "pose": "skipped", "physics": "skipped", "retrieval": "skipped", "coach": "fallback"},
        "motion_feedback": "不可用",
        "trajectory_points": 0,
        "analysis_quality": "degraded",
        "retrieval_summary": {},
        "physics_profile": {"attack_phase": "neutral", "tempo_profile": "medium", "shot_shape": "balanced-rally", "pressure_index": 0.0},
        "tracker_diagnostics": {},
        "motion_profile": {},
        "rally_quality": {},
        "confidence_report": {},
        "referee_audit": {},
        "sequence_context": {},
        "duel_projection": {},
    }
    return {
        "physics": {"event": "未知", "max_speed_kmh": 0.0, "description": "该片段无法完成分析。", "coordinates": [], "auto_result": "UNKNOWN", "match_type": match_type},
        "advice": advice,
        "tactics": [],
        "session_id": None,
        "match_type": match_type,
        "auto_result": "UNKNOWN",
        "auto_reward": 0.0,
        "summary": summary,
        "diagnostics": diagnostics,
        "report": {},
    }
