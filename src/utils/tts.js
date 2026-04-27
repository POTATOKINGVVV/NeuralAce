/**
 * TTS — Text-to-Speech voice coaching engine using Web Speech API.
 *
 * Features:
 *   - Priority-based speech (critical alerts interrupt lower priority)
 *   - Per-tag cooldown to avoid repeating the same advice
 *   - Chinese language support
 */

const PRIORITY_MAP = { critical: 3, high: 2, medium: 1, info: 0 };
const DEFAULT_COOLDOWN_MS = 10000;

class TTSEngine {
    constructor() {
        this._enabled = true;
        this._cooldowns = new Map();       // tag → last-spoken timestamp
        this._cooldownMs = DEFAULT_COOLDOWN_MS;
        this._currentPriority = -1;
        this._speaking = false;
    }

    get enabled() { return this._enabled; }
    set enabled(val) { this._enabled = !!val; }

    setCooldown(ms) { this._cooldownMs = ms; }

    /**
     * Speak a coaching alert.
     * @param {{ message: string, priority?: string, tag?: string }} alert
     */
    speak(alert) {
        if (!this._enabled) return;
        if (!window.speechSynthesis) return;

        const { message, priority = 'info', tag = '' } = alert;
        const prio = PRIORITY_MAP[priority] ?? 0;

        // Per-tag cooldown
        if (tag) {
            const lastTime = this._cooldowns.get(tag) || 0;
            if (Date.now() - lastTime < this._cooldownMs) return;
        }

        // If currently speaking something of equal or higher priority, skip
        if (this._speaking && prio <= this._currentPriority) return;

        // If higher priority, cancel current speech
        if (this._speaking && prio > this._currentPriority) {
            window.speechSynthesis.cancel();
        }

        const utterance = new SpeechSynthesisUtterance(message);
        utterance.lang = 'zh-CN';
        utterance.rate = priority === 'critical' ? 1.25 : 1.1;
        utterance.pitch = priority === 'critical' ? 1.1 : 1.0;
        utterance.volume = priority === 'critical' ? 1.0 : 0.85;

        utterance.onstart = () => {
            this._speaking = true;
            this._currentPriority = prio;
        };
        utterance.onend = () => {
            this._speaking = false;
            this._currentPriority = -1;
        };
        utterance.onerror = () => {
            this._speaking = false;
            this._currentPriority = -1;
        };

        if (tag) this._cooldowns.set(tag, Date.now());
        window.speechSynthesis.speak(utterance);
    }

    /**
     * Speak multiple alerts (from a WearableCoach response).
     * Highest priority first.
     */
    speakAlerts(alerts = []) {
        const sorted = [...alerts].sort(
            (a, b) => (PRIORITY_MAP[b.priority] || 0) - (PRIORITY_MAP[a.priority] || 0)
        );
        for (const alert of sorted) {
            this.speak(alert);
        }
    }

    stop() {
        if (window.speechSynthesis) window.speechSynthesis.cancel();
        this._speaking = false;
        this._currentPriority = -1;
    }
}

export const ttsEngine = new TTSEngine();
export default ttsEngine;
