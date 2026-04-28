"""Centralised English-key → Chinese-label translation for user-facing text."""

from __future__ import annotations

# ── attack_phase / phase values ──────────────────────────────────────────────
_PHASE_MAP: dict[str, str] = {
    "neutral": "中性",
    "advantage": "优势",
    "under_pressure": "被动",
    "under pressure": "被动",
    "transition": "过渡",
}

# ── court_context / channel values ───────────────────────────────────────────
_COURT_MAP: dict[str, str] = {
    "rear_channel": "后场通道",
    "rear channel": "后场通道",
    "front_channel": "前场通道",
    "front channel": "前场通道",
    "mid_channel": "中场通道",
    "mid channel": "中场通道",
    "A_deep_wide": "A侧深远",
    "A deep wide": "A侧深远",
    "B_deep_wide": "B侧深远",
    "B deep wide": "B侧深远",
    "center": "中心",
    "unknown": "未知",
}

# ── style_family values ──────────────────────────────────────────────────────
_STYLE_MAP: dict[str, str] = {
    "absorb-and-redirect": "吸收反击",
    "absorb and redirect": "吸收反击",
    "reset-and-rebuild": "重置重建",
    "reset and rebuild": "重置重建",
    "front-court-trap": "前场陷阱",
    "front court trap": "前场陷阱",
    "attritional-pressure": "消耗压力",
    "attritional pressure": "消耗压力",
    "compression-attack": "压缩进攻",
    "compression attack": "压缩进攻",
    "deception": "假动作",
    "interception": "截击",
    "managed-pressure": "控制压力",
    "managed pressure": "控制压力",
    "topspin-attack": "上旋进攻",
    "topspin attack": "上旋进攻",
    "short-game": "短球",
    "short game": "短球",
    "serve-variation": "发球变化",
    "serve variation": "发球变化",
    "balanced": "均衡",
    "direct-pressure": "直接施压",
    "direct pressure": "直接施压",
    "soft-control": "轻柔控制",
    "soft control": "轻柔控制",
    "flat-drive": "平抽",
    "flat drive": "平抽",
    "topspin-loop": "弧圈球",
    "topspin loop": "弧圈球",
    "spin-rally": "旋转相持",
    "spin rally": "旋转相持",
}

# ── policy_mode values ───────────────────────────────────────────────────────
_POLICY_MAP: dict[str, str] = {
    "explore": "探索",
    "exploit": "利用",
    "balanced": "均衡",
    "stabilize": "稳固",
}

# ── development_stage values ─────────────────────────────────────────────────
_STAGE_MAP: dict[str, str] = {
    "weaponize": "武器化",
    "refine": "精炼",
    "probe": "探索",
    "stabilize": "稳固",
}

# ── strategy_tag values ──────────────────────────────────────────────────────
_STRATEGY_MAP: dict[str, str] = {
    "adapt": "适应",
    "reinforce": "强化",
    "cooldown": "冷却",
    "explore": "探索",
    "exploit": "利用",
    "reinforce-success": "强化成功",
    "reinforce success": "强化成功",
    "cooldown-risk": "冷却风险",
    "cooldown risk": "冷却风险",
}

# ── streak_state / pressure_swing label values ───────────────────────────────
_STREAK_MAP: dict[str, str] = {
    "neutral": "中性",
    "winning": "连胜",
    "losing": "连败",
    "winning-streak": "连胜",
    "winning streak": "连胜",
    "losing-streak": "连败",
    "losing streak": "连败",
    "steady-pressure": "压力平稳",
    "steady pressure": "压力平稳",
    "rising-pressure": "压力上升",
    "rising pressure": "压力上升",
    "releasing-pressure": "压力释放",
    "releasing pressure": "压力释放",
    "volatile-pressure": "压力波动",
    "volatile pressure": "压力波动",
    "steady": "平稳",
}

# ── Merged lookup (order matters: more specific first) ───────────────────────
_MERGED: dict[str, str] = {}
for _m in (_COURT_MAP, _STYLE_MAP, _PHASE_MAP, _POLICY_MAP, _STAGE_MAP, _STRATEGY_MAP, _STREAK_MAP):
    _MERGED.update(_m)


def zh(key: str) -> str:
    """Translate an internal English key to a Chinese label.

    If the key is already Chinese or not in the map the original value is
    returned unchanged so the function is always safe to call.
    """
    if not key:
        return key
    normalised = key.strip()
    hit = _MERGED.get(normalised)
    if hit:
        return hit
    # Also try after common separator normalisation
    for old, new in (("-", " "), ("_", " ")):
        alt = normalised.replace(old, new)
        hit = _MERGED.get(alt)
        if hit:
            return hit
    return normalised


def zh_phase(value: str) -> str:
    """Translate attack_phase / phase values."""
    return _PHASE_MAP.get(value, _PHASE_MAP.get(value.replace("_", " "), value))


def zh_court(value: str) -> str:
    """Translate court_context values."""
    return _COURT_MAP.get(value, _COURT_MAP.get(value.replace("_", " "), value))


def zh_style(value: str) -> str:
    """Translate style_family values."""
    return _STYLE_MAP.get(value, _STYLE_MAP.get(value.replace("-", " "), value))


def zh_policy(value: str) -> str:
    """Translate policy_mode values."""
    return _POLICY_MAP.get(value, value)


def zh_stage(value: str) -> str:
    """Translate development_stage values."""
    return _STAGE_MAP.get(value, value)


def zh_strategy(value: str) -> str:
    """Translate strategy_tag values."""
    return _STRATEGY_MAP.get(value, value)
