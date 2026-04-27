"""
Wearable Coach — real-time AI coaching driven by Mi Band 6 IMU + heart-rate data.

Components:
  SwingDetector   : detects badminton swing events from accelerometer peaks
  WearableCoach   : fuses HR + IMU analysis to produce voice-ready coaching alerts
"""

import math
import time
from collections import deque
from typing import Optional


# ── Swing Detector ──────────────────────────────────────────────────────────

class SwingDetector:
    """Detects badminton swing events from raw IMU acceleration magnitude peaks."""

    SWING_ACCEL_THRESHOLD = 25.0   # m/s², minimum peak to count as a swing
    SWING_COOLDOWN = 0.4           # seconds between distinct swings
    HISTORY_SIZE = 200             # keep last N swings for fatigue analysis

    def __init__(self):
        self.last_swing_time: float = 0.0
        self.swing_history: deque = deque(maxlen=self.HISTORY_SIZE)
        self.raw_buffer: deque = deque(maxlen=500)

    def feed(self, sample: dict) -> Optional[dict]:
        """
        Feed one IMU sample.  Returns a swing-event dict if a swing is detected,
        otherwise None.

        Expected sample keys:
            accelX, accelY, accelZ  (m/s²)
            gyroX, gyroY, gyroZ    (°/s, optional)
            timestamp              (ms epoch)
        """
        ax = sample.get("accelX", 0.0)
        ay = sample.get("accelY", 0.0)
        az = sample.get("accelZ", 0.0)
        accel_mag = math.sqrt(ax * ax + ay * ay + az * az)

        self.raw_buffer.append({**sample, "accel_magnitude": accel_mag})

        ts = sample.get("timestamp", time.time() * 1000) / 1000.0  # → seconds

        if accel_mag < self.SWING_ACCEL_THRESHOLD:
            return None
        if ts - self.last_swing_time < self.SWING_COOLDOWN:
            return None

        self.last_swing_time = ts

        gx = sample.get("gyroX", 0.0)
        gy = sample.get("gyroY", 0.0)
        gz = sample.get("gyroZ", 0.0)
        gyro_mag = math.sqrt(gx * gx + gy * gy + gz * gz)

        swing_event = {
            "type": "swing",
            "timestamp": ts,
            "peak_accel": round(accel_mag, 2),
            "gyro_magnitude": round(gyro_mag, 2),
            "intensity": self._classify_intensity(accel_mag),
            "swing_count": len(self.swing_history) + 1,
            "fatigue_index": 0.0,
        }

        self.swing_history.append(swing_event)
        swing_event["fatigue_index"] = self._calc_fatigue()
        return swing_event

    # ── Intensity classification ────────────────────────────────────────

    @staticmethod
    def _classify_intensity(accel: float) -> str:
        if accel > 60:
            return "smash"
        if accel > 40:
            return "drive"
        if accel > 25:
            return "clear"
        return "tap"

    # ── Fatigue: compare recent vs early swing peaks ────────────────────

    def _calc_fatigue(self) -> float:
        n = len(self.swing_history)
        if n < 20:
            return 0.0
        history = list(self.swing_history)
        early  = history[:10]
        recent = history[-10:]
        avg_early  = sum(s["peak_accel"] for s in early) / 10.0
        avg_recent = sum(s["peak_accel"] for s in recent) / 10.0
        if avg_early == 0:
            return 0.0
        return round(max(0.0, 1.0 - avg_recent / avg_early), 3)

    def reset(self):
        self.last_swing_time = 0.0
        self.swing_history.clear()
        self.raw_buffer.clear()


# ── Wearable Coach ──────────────────────────────────────────────────────────

class WearableCoach:
    """
    Fuses heart-rate zones + IMU swing analysis to produce real-time
    coaching alerts suitable for TTS voice output.
    """

    HR_ZONES = {
        "recovery":  (0, 120),
        "aerobic":   (120, 150),
        "threshold": (150, 170),
        "anaerobic": (170, 185),
        "redline":   (185, 999),
    }

    # Minimum interval (seconds) between alerts of the same tag
    ALERT_COOLDOWN = 8.0

    def __init__(self):
        self.swing_detector = SwingDetector()
        self._last_alert_times: dict[str, float] = {}
        self._latest_hr: int = 0
        self._latest_hr_zone: str = "recovery"

    # ── Main entry point ────────────────────────────────────────────────

    def evaluate(self, sensor_data: dict) -> list[dict]:
        """
        Evaluate one sensor sample (may contain IMU + HR).
        Returns a list of coaching alert dicts (may be empty).

        Each alert: { priority, message, tag, timestamp }
        """
        now = time.time()
        alerts: list[dict] = []

        # Update heart rate if present
        hr = sensor_data.get("heartRate") or sensor_data.get("bpm") or 0
        if hr > 0:
            self._latest_hr = hr
            self._latest_hr_zone = self._hr_zone(hr)

        # ── Heart rate alerts ───────────────────────────────────────────
        if self._latest_hr > 0:
            if self._latest_hr_zone == "redline":
                alerts.append(self._make_alert(
                    "critical",
                    f"心率{self._latest_hr}过高！下一拍用高远球过渡，争取恢复时间",
                    "hr_redline", now,
                ))
            elif self._latest_hr_zone == "anaerobic":
                alerts.append(self._make_alert(
                    "high",
                    f"心率{self._latest_hr}偏高，控制节奏，避免连续起跳",
                    "hr_high", now,
                ))

        # ── IMU swing analysis ──────────────────────────────────────────
        swing = self.swing_detector.feed(sensor_data)
        if swing:
            # Fatigue warning
            if swing["fatigue_index"] > 0.3:
                pct = int(swing["fatigue_index"] * 100)
                alerts.append(self._make_alert(
                    "high",
                    f"挥拍力量下降{pct}%，注意发力效率，多用手腕内旋",
                    "fatigue", now,
                ))

            # Smash follow-up
            if swing["intensity"] == "smash":
                alerts.append(self._make_alert(
                    "info",
                    "杀球力度充足，杀球后立即回中准备下一拍",
                    "swing_smash", now,
                ))

            # Weak swing under high HR
            if swing["intensity"] == "tap" and self._latest_hr > 160:
                alerts.append(self._make_alert(
                    "medium",
                    "高心率下挥拍偏软，建议主动发力或选择放网控制节奏",
                    "weak_swing", now,
                ))

            # Low wrist rotation (pronation) on power shots
            if swing["gyro_magnitude"] < 3.0 and swing["intensity"] in ("drive", "smash"):
                alerts.append(self._make_alert(
                    "medium",
                    "手腕旋转不足，正手击球注意内旋发力增加拍面速度",
                    "low_pronation", now,
                ))

            # Swing rhythm: if interval between last two swings is very short
            history = list(self.swing_detector.swing_history)
            if len(history) >= 2:
                gap = history[-1]["timestamp"] - history[-2]["timestamp"]
                if gap < 0.8 and self._latest_hr > 170:
                    alerts.append(self._make_alert(
                        "medium",
                        "连续快速对抗中，注意呼吸节奏，寻找机会打出制胜分",
                        "rapid_exchange", now,
                    ))

        # Filter by cooldown
        return [a for a in alerts if a is not None]

    # ── Heart rate zone lookup ──────────────────────────────────────────

    def _hr_zone(self, hr: int) -> str:
        for zone, (lo, hi) in self.HR_ZONES.items():
            if lo <= hr < hi:
                return zone
        return "recovery"

    # ── Alert factory with cooldown ─────────────────────────────────────

    def _make_alert(self, priority: str, message: str, tag: str, now: float) -> Optional[dict]:
        last = self._last_alert_times.get(tag, 0.0)
        if now - last < self.ALERT_COOLDOWN:
            return None
        self._last_alert_times[tag] = now
        return {
            "priority": priority,
            "message": message,
            "tag": tag,
            "timestamp": now,
        }

    # ── State getters (for injecting into LLM prompt) ──────────────────

    def get_physical_state(self) -> dict:
        """Return a summary dict suitable for injecting into CoachAgent prompts."""
        history = list(self.swing_detector.swing_history)
        recent_swings = history[-5:] if history else []
        return {
            "heart_rate": self._latest_hr,
            "hr_zone": self._latest_hr_zone,
            "total_swings": len(history),
            "fatigue_index": self.swing_detector._calc_fatigue(),
            "recent_intensities": [s["intensity"] for s in recent_swings],
            "avg_peak_accel": (
                round(sum(s["peak_accel"] for s in recent_swings) / len(recent_swings), 1)
                if recent_swings else 0.0
            ),
        }

    def reset(self):
        self.swing_detector.reset()
        self._last_alert_times.clear()
        self._latest_hr = 0
        self._latest_hr_zone = "recovery"
