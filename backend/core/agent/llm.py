import asyncio
import json

import openai

from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL_NAME


# ---------------------------------------------------------------------------
# System Prompt Registry
# ---------------------------------------------------------------------------

SYSTEM_PROMPT_REGISTRY: dict[str, str] = {
    "badminton": (
        "You are a world-class badminton AI coach powered by Bayesian learning. "
        "You analyze shuttle trajectory, court zones, speed profiles, and pressure "
        "phases to give concise tactical advice."
    ),
    "table_tennis": (
        "You are a National-level Table Tennis Coach powered by Bayesian learning. "
        "You interpret bounce counts, table zones (near-net vs deep), ball speed, "
        "and spin indicators to advise on technique. "
        "Your vocabulary includes topspin, underspin (backspin), sidespin, fast push, "
        "loop drive, chop block, flick, and counter-topspin. "
        "Always reason about spin type, placement, and tempo when giving advice."
    ),
}


def _build_user_prompt(state: dict, tactic_text: str, sport_type: str) -> str:
    """Build the sport-aware user prompt injected after the system message."""

    # Common state block shared by all sports.
    lines = [
        "Current rally state:",
        f"- Event: {state.get('event', 'unknown')} ({state.get('max_speed_kmh', 0)} km/h)",
        f"- Description: {state.get('description', '')}",
        f"- Attack phase: {state.get('attack_phase', 'neutral')}",
        f"- Tempo profile: {state.get('tempo_profile', 'medium')}",
        f"- Pressure index: {state.get('pressure_index', 0.0)}",
        f"- Court context: {state.get('court_context', 'unknown')}",
    ]

    if sport_type == "table_tennis":
        lines += [
            f"- Bounce count: {state.get('bounce_count', 'N/A')}",
            f"- Last bounce side: {state.get('last_bounce_side', 'N/A')}",
            f"- Winning side: {state.get('winning_side', 'N/A')}",
        ]
    else:
        lines.append(f"- Shot shape: {state.get('shot_shape', 'balanced-rally')}")

    lines += [
        "",
        "Recommended tactics:",
        tactic_text,
        "",
        "Return strict JSON with exactly these keys:",
        "- text",
        "- headline",
        "- focus",
        "- next_step",
        "- confidence_label",
        "",
        "Rules:",
        "- Keep `text` under 24 words.",
        "- Keep `headline` under 8 words.",
        '- `focus` should be a short training area such as "Recovery", "Defense", or "Shot selection".',
        "- `next_step` should be one short actionable instruction.",
        "- `confidence_label` must be one of: high, medium, low.",
        "- Prefer the top tactic unless its risk is obviously too high for the current rally phase.",
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
        top_tactic = tactics[0]["name"] if tactics else state.get("event", "the next pattern")
        next_step = tactics[0].get("recommended_action", "Prepare for the next shot early.") if tactics else "Prepare for the next shot early."
        confidence_label = tactics[0].get("confidence_label", "medium") if tactics else "medium"
        focus = state.get("attack_phase", "Shot selection").replace("_", " ").title()
        if sport_type == "table_tennis":
            default_text = "Read the spin, stay compact, and control your placement."
        else:
            default_text = "Stay balanced, recover fast, and prepare for the next contact."
        return {
            "text": default_text,
            "headline": f"Play into {top_tactic}",
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
