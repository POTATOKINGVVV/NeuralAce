import asyncio
import json

import openai

from core.utils.label_zh import zh_phase

from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL_NAME


# ---------------------------------------------------------------------------
# System Prompt Registry
# ---------------------------------------------------------------------------

SYSTEM_PROMPT_REGISTRY: dict[str, str] = {
    "badminton": (
        "You are a world-class badminton AI coach powered by Bayesian learning. "
        "You analyze shuttle trajectory, court zones, speed profiles, and pressure "
        "phases to give concise tactical advice. "
        "You MUST respond entirely in Chinese (Simplified Chinese)."
    ),
    "table_tennis": (
        "You are a National-level Table Tennis Coach powered by Bayesian learning. "
        "You interpret bounce counts, table zones (near-net vs deep), ball speed, "
        "and spin indicators to advise on technique. "
        "Your vocabulary includes topspin, underspin (backspin), sidespin, fast push, "
        "loop drive, chop block, flick, and counter-topspin. "
        "Always reason about spin type, placement, and tempo when giving advice. "
        "You MUST respond entirely in Chinese (Simplified Chinese)."
    ),
}


def _build_user_prompt(state: dict, tactic_text: str, sport_type: str) -> str:
    """Build the sport-aware user prompt injected after the system message."""

    # Common state block shared by all sports.
    lines = [
        "\u5f53\u524d\u56de\u5408\u72b6\u6001:",
        f"- \u4e8b\u4ef6: {state.get('event', 'unknown')} ({state.get('max_speed_kmh', 0)} km/h)",
        f"- \u63cf\u8ff0: {state.get('description', '')}",
        f"- \u8fdb\u653b\u9636\u6bb5: {state.get('attack_phase', 'neutral')}",
        f"- \u8282\u594f\u6a21\u5f0f: {state.get('tempo_profile', 'medium')}",
        f"- \u538b\u529b\u6307\u6570: {state.get('pressure_index', 0.0)}",
        f"- \u573a\u5730\u533a\u57df: {state.get('court_context', 'unknown')}",
    ]

    if sport_type == "table_tennis":
        lines += [
            f"- \u5f39\u8df3\u6b21\u6570: {state.get('bounce_count', 'N/A')}",
            f"- \u6700\u540e\u5f39\u8df3\u4fa7: {state.get('last_bounce_side', 'N/A')}",
            f"- \u5f97\u5206\u65b9: {state.get('winning_side', 'N/A')}",
        ]
    else:
        lines.append(f"- \u51fb\u7403\u5f62\u6001: {state.get('shot_shape', 'balanced-rally')}")

    lines += [
        "",
        "\u63a8\u8350\u6218\u672f:",
        tactic_text,
        "",
        "\u8fd4\u56de\u4e25\u683c\u7684 JSON\uff0c\u5305\u542b\u4ee5\u4e0b\u952e:",
        "- text",
        "- headline",
        "- focus",
        "- next_step",
        "- confidence_label",
        "",
        "\u89c4\u5219:",
        "- `text` \u4e0d\u8d85\u8fc7 30 \u4e2a\u4e2d\u6587\u5b57\u3002",
        "- `headline` \u4e0d\u8d85\u8fc7 10 \u4e2a\u4e2d\u6587\u5b57\u3002",
        '- `focus` \u5e94\u4e3a\u7b80\u77ed\u7684\u8bad\u7ec3\u65b9\u5411\uff0c\u4f8b\u5982 "\u6062\u590d\u8c03\u6574"\u3001"\u9632\u5b88\u7a33\u56fa"\u3001"\u843d\u70b9\u63a7\u5236"\u3002',
        "- `next_step` \u5e94\u4e3a\u4e00\u6761\u7b80\u77ed\u7684\u53ef\u6267\u884c\u5efa\u8bae\u3002",
        "- `confidence_label` \u5fc5\u987b\u4e3a high\u3001medium\u3001low \u4e4b\u4e00\u3002",
        "- \u4f18\u5148\u9009\u62e9\u6392\u540d\u7b2c\u4e00\u7684\u6218\u672f\uff0c\u9664\u975e\u5176\u98ce\u9669\u660e\u663e\u8fc7\u9ad8\u3002",
        "- \u6240\u6709\u8f93\u51fa\u5fc5\u987b\u4e3a\u4e2d\u6587\uff08\u7b80\u4f53\u4e2d\u6587\uff09\u3002",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CoachAgent
# ---------------------------------------------------------------------------

class CoachAgent:
    def __init__(self):
        self.client = openai.OpenAI(
            api_key=LLM_API_KEY,
            base_url=LLM_BASE_URL,
        )
        self.async_client = openai.AsyncOpenAI(
            api_key=LLM_API_KEY,
            base_url=LLM_BASE_URL,
        )

    def _format_tactics(self, tactics):
        if tactics:
            tactic_lines = []
            for index, tactic in enumerate(tactics, start=1):
                metadata = tactic["metadata"]
                alpha = metadata.get("alpha", 1.0)
                beta = metadata.get("beta", 1.0)
                win_probability = alpha / (alpha + beta) * 100 if alpha + beta else 50.0
                label = tactic.get("name") or tactic.get("content") or f"Tactic {index}"
                fit_breakdown = tactic.get("fit_breakdown", {})
                tactic_lines.append(
                    f"{index}. {label}\n"
                    f"   Summary: {tactic.get('content', label)}\n"
                    f"   Score: {tactic['score']:.2f} | Expected win rate: {win_probability:.1f}%\n"
                    f"   Context fit: {tactic.get('context_score', 0.0):.2f} | Risk penalty: {tactic.get('risk_penalty', 0.0):.2f}\n"
                    f"   Fit breakdown: {json.dumps(fit_breakdown)}"
                )
            return "\n".join(tactic_lines)
        return "No tactic recommendations are available."

    def _fallback_payload(self, state, tactics, sport_type="badminton"):
        top_tactic = tactics[0]["name"] if tactics else state.get("event", "\u4e0b\u4e00\u62cd")
        next_step = tactics[0].get("recommended_action", "\u63d0\u524d\u51c6\u5907\u4e0b\u4e00\u62cd\u51fb\u7403\u3002") if tactics else "\u63d0\u524d\u51c6\u5907\u4e0b\u4e00\u62cd\u51fb\u7403\u3002"
        confidence_label = tactics[0].get("confidence_label", "medium") if tactics else "medium"
        focus = zh_phase(state.get("attack_phase", "落点控制"))
        if sport_type == "table_tennis":
            default_text = "\u5224\u65ad\u65cb\u8f6c\uff0c\u4fdd\u6301\u7d27\u51d1\uff0c\u63a7\u5236\u843d\u70b9\u3002"
        else:
            default_text = "\u4fdd\u6301\u5e73\u8861\uff0c\u5feb\u901f\u8fd8\u539f\uff0c\u63d0\u524d\u51c6\u5907\u4e0b\u4e00\u62cd\u3002"
        return {
            "text": default_text,
            "headline": f"\u6267\u884c {top_tactic}",
            "focus": focus,
            "next_step": next_step,
            "confidence_label": confidence_label,
            "source": "fallback",
        }

    # ------------------------------------------------------------------
    # Async entry point (preferred in FastAPI handlers)
    # ------------------------------------------------------------------

    async def generate_structured_advice_async(self, state, tactics, sport_type="badminton"):
        tactic_text = self._format_tactics(tactics)
        system_prompt = SYSTEM_PROMPT_REGISTRY.get(sport_type, SYSTEM_PROMPT_REGISTRY["badminton"])
        user_prompt = _build_user_prompt(state, tactic_text, sport_type)

        try:
            response = await self.async_client.chat.completions.create(
                model=LLM_MODEL_NAME,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7,
                max_tokens=120,
            )
            content = response.choices[0].message.content
            payload = json.loads(content)
            payload["source"] = "llm"
            return payload
        except Exception:
            return self._fallback_payload(state, tactics, sport_type)

    # ------------------------------------------------------------------
    # Sync wrappers (backward-compatible with existing service layer)
    # ------------------------------------------------------------------

    def generate_structured_advice(self, state, tactics, sport_type="badminton"):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # Already inside an async context (e.g. FastAPI) – schedule and
            # use a thread so we don't block the event loop.
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(
                    asyncio.run,
                    self.generate_structured_advice_async(state, tactics, sport_type),
                ).result()
        return asyncio.run(self.generate_structured_advice_async(state, tactics, sport_type))

    def generate_advice(self, state, tactics, sport_type="badminton"):
        return self.generate_structured_advice(state, tactics, sport_type).get(
            "text", "Stay balanced, recover fast, and prepare for the next contact."
        )
