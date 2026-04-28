# core/physics/table_referee.py

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np
from scipy.signal import find_peaks, savgol_filter

from config import TABLE_LENGTH, TABLE_WIDTH


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class BounceEvent:
    """A single detected bounce with its spatial classification."""

    frame_index: int
    x: float
    y: float
    side: str          # "A", "B", or "OUT"
    in_bounds: bool
    confidence: float

    def to_dict(self) -> Dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# TableTennisReferee
# ---------------------------------------------------------------------------

class TableTennisReferee:
    """Auto-referee for table tennis based on bounce analysis.

    Public interface mirrors the badminton :class:`AutoReferee` closely so that
    :class:`PhysicsEngine` / strategy layers can consume it without adapters.

    Key methods
    -----------
    * ``find_bounces(trajectory, fps)`` – detect table bounces from the raw
      (x, y) pixel-coordinate time-series via vertical local-maxima analysis.
    * ``classify_side(x, y, corners, net_line)`` – map a bounce to a table
      side ("A" / "B") or "OUT".
    * ``evaluate_rally(trajectory, fps, corners, net_line, match_type)`` –
      full auto-referee pass returning a dict compatible with the badminton
      ``AutoReferee.judge_details`` output shape.
    """

    def __init__(
        self,
        bounce_prominence: float = 6.0,
        bounce_distance: int = 5,
        min_bounces: int = 1,
        oob_margin_px: float = 8.0,
    ):
        self.bounce_prominence = bounce_prominence
        self.bounce_distance = bounce_distance
        self.min_bounces = min_bounces
        self.oob_margin_px = oob_margin_px

    # ------------------------------------------------------------------
    # 1. Bounce Detection
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Tuning constants (class-level for easy override / testing)
    # ------------------------------------------------------------------
    _SAVGOL_WINDOW: int = 7        # Savitzky-Golay window length (must be odd)
    _SAVGOL_POLY: int = 2          # Savitzky-Golay polynomial order
    _PROM_FRAC: float = 0.05       # Adaptive prominence = 5% of y-range
    _PROM_MIN_PX: float = 8.0      # Minimum prominence in pixels
    _MIN_BOUNCE_GAP_SEC: float = 0.25  # Physical min time between two bounces
    _MAX_BOUNCES_PER_SEC: float = 2.5  # Physical upper-bound rate
    _CONF_THRESHOLD: float = 0.15  # Drop peaks below this confidence
    _MIN_RISE_FALL_PX: float = 3.0 # Minimum rise or fall around a peak

    def find_bounces(
        self,
        trajectory: Sequence[Tuple[int, int]],
        fps: float,
    ) -> List[Dict]:
        """Detect bounces by finding local maxima in the y-coordinate signal.

        In most broadcast / overhead camera setups the ball *drops* (y
        increases) toward the table and *rises* (y decreases) after a bounce.
        A bounce therefore appears as a **local maximum** in the y signal.

        Pipeline (P2 optimised):
        1. NaN-fill missing frames → linear interpolation.
        2. Savitzky-Golay smoothing (window=7, poly=2).
        3. Adaptive prominence (5 % of y-range, min 8 px) and fps-based
           minimum distance between peaks.
        4. Post-detection filters: confidence gate, rise/fall validation,
           maximum-rate cap.

        Returns a list of dicts (one per bounce) with keys ``frame_index``,
        ``x``, ``y``, and ``confidence``.
        """
        coords = np.array(trajectory, dtype=np.float64)
        if len(coords) < 3:
            return []

        y_signal = coords[:, 1].copy()

        # Replace missing (0, 0) frames with NaN so they don't create
        # artificial peaks, then interpolate for find_peaks.
        missing = (coords[:, 0] == 0) & (coords[:, 1] == 0)
        y_signal[missing] = np.nan

        # Linear interpolation over NaN gaps.
        nans = np.isnan(y_signal)
        if nans.all():
            return []
        if nans.any():
            valid_idx = np.where(~nans)[0]
            y_signal = np.interp(
                np.arange(len(y_signal)),
                valid_idx,
                y_signal[valid_idx],
            )

        # --- Stage 1: Savitzky-Golay smoothing ---
        win = min(self._SAVGOL_WINDOW, len(y_signal))
        if win % 2 == 0:
            win = max(win - 1, 3)
        if len(y_signal) >= win >= 3 and win > self._SAVGOL_POLY:
            y_smooth = savgol_filter(y_signal, win, self._SAVGOL_POLY)
        else:
            y_smooth = y_signal.copy()

        # --- Stage 2: Adaptive thresholds ---
        y_range = float(np.ptp(y_smooth))  # peak-to-peak amplitude
        adaptive_prom = max(y_range * self._PROM_FRAC, self._PROM_MIN_PX)
        adaptive_dist = max(int(fps * self._MIN_BOUNCE_GAP_SEC), self.bounce_distance)

        peak_indices, properties = find_peaks(
            y_smooth,
            prominence=adaptive_prom,
            distance=adaptive_dist,
        )

        prominences = properties.get("prominences", np.zeros(len(peak_indices)))

        # --- Stage 3: Build raw bounce list ---
        raw_bounces: List[Dict] = []
        for i, idx in enumerate(peak_indices):
            prom = float(prominences[i]) if i < len(prominences) else 0.0
            conf = float(np.clip(prom / max(adaptive_prom * 3, 1e-6), 0.0, 1.0))
            raw_bounces.append(
                {
                    "frame_index": int(idx),
                    "x": float(coords[idx, 0]),
                    "y": float(coords[idx, 1]),
                    "confidence": round(conf, 3),
                    "_y_smooth": float(y_smooth[idx]),
                }
            )

        # --- Stage 4: Post-detection plausibility filters ---
        bounces = self._filter_bounces(raw_bounces, y_smooth, fps, len(coords))
        return bounces

    def _filter_bounces(
        self,
        raw: List[Dict],
        y_smooth: np.ndarray,
        fps: float,
        n_frames: int,
    ) -> List[Dict]:
        """Apply physical plausibility filters to raw bounce candidates."""
        if not raw:
            return []

        kept: List[Dict] = []

        for b in raw:
            # 4a. Confidence gate
            if b["confidence"] < self._CONF_THRESHOLD:
                continue

            # 4b. Rise-fall validation: the peak must have a visible dip on
            #     at least one side (ball went up *before* or *after* the peak).
            idx = b["frame_index"]
            look = max(int(fps * 0.15), 3)  # ~150 ms window
            left_min = float(np.min(y_smooth[max(0, idx - look): idx])) if idx > 0 else b["_y_smooth"]
            right_min = float(np.min(y_smooth[idx + 1: min(len(y_smooth), idx + look + 1)])) if idx < len(y_smooth) - 1 else b["_y_smooth"]
            rise = b["_y_smooth"] - left_min
            fall = b["_y_smooth"] - right_min
            if rise < self._MIN_RISE_FALL_PX and fall < self._MIN_RISE_FALL_PX:
                continue

            kept.append(b)

        # 4c. Maximum rate cap: keep at most N bounces per second of footage.
        duration_sec = n_frames / max(fps, 1.0)
        max_allowed = max(int(duration_sec * self._MAX_BOUNCES_PER_SEC), 2)
        if len(kept) > max_allowed:
            # Keep the top-confidence ones.
            kept.sort(key=lambda b: b["confidence"], reverse=True)
            kept = kept[:max_allowed]
            kept.sort(key=lambda b: b["frame_index"])

        # Strip internal helper key before returning.
        for b in kept:
            b.pop("_y_smooth", None)

        return kept

    # ------------------------------------------------------------------
    # 2. Zone Mapping
    # ------------------------------------------------------------------

    def classify_side(
        self,
        x: float,
        y: float,
        corners: np.ndarray,
        net_line: Tuple[Tuple[float, float], Tuple[float, float]],
    ) -> str:
        """Determine whether a point lies on side A, side B, or out of bounds.

        *Side A* is defined as the half above/left of the net line (the side
        closer to corners[0] / TL).  *Side B* is the opposite half.

        Parameters
        ----------
        corners : np.ndarray (4, 2)
            Table corners in [TL, TR, BR, BL] order.
        net_line : ((x1, y1), (x2, y2))
            The two endpoints of the net across the table.
        """
        table_polygon = corners.astype(np.float32).reshape(-1, 1, 2)
        dist = cv2.pointPolygonTest(table_polygon, (float(x), float(y)), True)

        if dist < -self.oob_margin_px:
            return "OUT"

        # Signed distance to the net line (positive = side A, negative = side B).
        (nx1, ny1), (nx2, ny2) = net_line
        cross = (nx2 - nx1) * (y - ny1) - (ny2 - ny1) * (x - nx1)
        return "A" if cross <= 0 else "B"

    # ------------------------------------------------------------------
    # 3. Auto-Referee Logic
    # ------------------------------------------------------------------

    def evaluate_rally(
        self,
        trajectory: Sequence[Tuple[int, int]],
        fps: float,
        corners: np.ndarray,
        net_line: Tuple[Tuple[float, float], Tuple[float, float]],
        match_type: str = "singles",
    ) -> Dict:
        """Full auto-referee evaluation of a rally.

        Rules applied (simplified ITF table tennis):
        * Valid continuation: A-side bounce → net crossing → B-side bounce
          (and vice-versa).
        * Double bounce on one side → opposing player wins the point.
        * Trajectory ends outside the table polygon after the net crossing →
          ``FAULT`` (out of bounds).

        Returns
        -------
        dict
            Keys mirror the badminton ``AutoReferee.judge_details`` shape:
            ``auto_result``, ``referee_confidence``, ``referee_reason``,
            ``bounces``, ``court_context``, ``last_hitter``, etc.
        """
        raw_bounces = self.find_bounces(trajectory, fps)

        # Annotate each bounce with its side.
        bounce_events: List[BounceEvent] = []
        for b in raw_bounces:
            side = self.classify_side(b["x"], b["y"], corners, net_line)
            bounce_events.append(
                BounceEvent(
                    frame_index=b["frame_index"],
                    x=b["x"],
                    y=b["y"],
                    side=side,
                    in_bounds=(side != "OUT"),
                    confidence=b["confidence"],
                )
            )

        if len(bounce_events) < self.min_bounces:
            return self._insufficient_signal(bounce_events, match_type)

        auto_result, reason, winning_side = self._apply_rules(bounce_events)
        last_hitter = self._infer_last_hitter(bounce_events)
        referee_confidence = self._estimate_confidence(bounce_events, auto_result)
        court_context = self._court_context(bounce_events, corners, net_line)

        return {
            "auto_result": auto_result,
            "referee_confidence": round(referee_confidence, 3),
            "referee_reason": reason,
            "bounces": [be.to_dict() for be in bounce_events],
            "bounce_count": len(bounce_events),
            "court_context": court_context,
            "last_hitter": last_hitter,
            "winning_side": winning_side,
            "is_in": bounce_events[-1].in_bounds if bounce_events else None,
            "landing_point": [bounce_events[-1].x, bounce_events[-1].y] if bounce_events else None,
            "landing_confidence": round(bounce_events[-1].confidence, 3) if bounce_events else 0.0,
            "direction_consistency": round(self._direction_consistency(trajectory), 3),
            "landing_margin": 0.0,
            "match_type": match_type,
            "referee_trace": {
                "decision": auto_result.lower(),
                "rule_chain": reason,
                "bounce_sides": [be.side for be in bounce_events],
            },
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _apply_rules(
        self, bounces: List[BounceEvent]
    ) -> Tuple[str, str, Optional[str]]:
        """Walk the bounce sequence and apply table-tennis point rules.

        Returns ``(auto_result, reason, winning_side)``.
        """
        # Filter to in-bounds bounces for the core alternation check.
        in_bounds = [b for b in bounces if b.in_bounds]

        # --- Out-of-bounds termination ---
        if bounces and not bounces[-1].in_bounds:
            # Last bounce was OUT – the hitter faulted.
            last_in = in_bounds[-1] if in_bounds else None
            if last_in is not None:
                faulting = last_in.side
                winner = "B" if faulting == "A" else "A"
                return (
                    "FAULT",
                    f"球在 {faulting} 侧最后一次有效弹跳后落到界外。",
                    winner,
                )
            return ("FAULT", "球落到界外，无有效台面弹跳。", None)

        # --- Double-bounce detection ---
        for i in range(1, len(in_bounds)):
            if in_bounds[i].side == in_bounds[i - 1].side:
                double_side = in_bounds[i].side
                winner = "B" if double_side == "A" else "A"
                result = "WIN" if winner == "A" else "LOSS"
                return (
                    result,
                    (
                        f"{double_side} 侧检测到二次弹跳"
                        f"（帧 {in_bounds[i - 1].frame_index} → {in_bounds[i].frame_index}）。"
                        f"{winner} 侧得分。"
                    ),
                    winner,
                )

        # --- No violation detected – rally is still valid / inconclusive ---
        if len(in_bounds) >= 2:
            return (
                "UNKNOWN",
                f"回合有效，共 {len(in_bounds)} 次交替弹跳；"
                "尚未有明确得分。",
                None,
            )

        return ("UNKNOWN", "弹跳数据不足，无法做出判定。", None)

    def _infer_last_hitter(self, bounces: List[BounceEvent]) -> str:
        """Infer who hit last based on the last in-bounds bounce side.

        Convention: Side A = USER, Side B = OPPONENT.
        """
        for b in reversed(bounces):
            if b.in_bounds:
                return "USER" if b.side == "A" else "OPPONENT"
        return "UNKNOWN"

    def _estimate_confidence(
        self, bounces: List[BounceEvent], auto_result: str
    ) -> float:
        if not bounces:
            return 0.1
        mean_conf = float(np.mean([b.confidence for b in bounces]))
        count_factor = float(np.clip(len(bounces) / 6.0, 0.0, 1.0))
        in_ratio = float(
            np.clip(
                sum(1 for b in bounces if b.in_bounds) / max(len(bounces), 1),
                0.0,
                1.0,
            )
        )
        decisiveness = 0.85 if auto_result in ("WIN", "LOSS", "FAULT") else 0.45
        return float(
            np.clip(
                0.30 * mean_conf + 0.25 * count_factor + 0.20 * in_ratio + 0.25 * decisiveness,
                0.0,
                1.0,
            )
        )

    def _direction_consistency(
        self, trajectory: Sequence[Tuple[int, int]]
    ) -> float:
        coords = np.array(trajectory, dtype=np.float64)
        valid = coords[(coords[:, 0] > 0) | (coords[:, 1] > 0)]
        if len(valid) < 3:
            return 0.2
        dy = np.diff(valid[:, 1])
        signs = np.sign(dy)
        non_zero = signs[signs != 0]
        if len(non_zero) == 0:
            return 0.25
        dominant = 1 if np.sum(non_zero > 0) >= np.sum(non_zero < 0) else -1
        return float(np.mean(non_zero == dominant))

    def _court_context(
        self,
        bounces: List[BounceEvent],
        corners: np.ndarray,
        net_line: Tuple[Tuple[float, float], Tuple[float, float]],
    ) -> str:
        """Describe the spatial context of the last bounce relative to the table."""
        if not bounces:
            return "unknown"

        last = bounces[-1]
        if not last.in_bounds:
            return "out_of_bounds"

        (nx1, ny1), (nx2, ny2) = net_line
        net_center_x = (nx1 + nx2) / 2.0
        net_center_y = (ny1 + ny2) / 2.0
        table_w = float(np.linalg.norm(corners[1] - corners[0]))
        table_h = float(np.linalg.norm(corners[3] - corners[0]))

        # Depth: distance from net along the table's long axis.
        depth_frac = abs(last.y - net_center_y) / max(table_h / 2.0, 1e-6)
        if depth_frac < 0.33:
            depth = "net"
        elif depth_frac < 0.66:
            depth = "mid"
        else:
            depth = "deep"

        # Width: lateral position.
        width_frac = abs(last.x - net_center_x) / max(table_w / 2.0, 1e-6)
        if width_frac < 0.33:
            width = "central"
        elif width_frac < 0.75:
            width = "channel"
        else:
            width = "wide"

        return f"{last.side}_{depth}_{width}"

    def _insufficient_signal(
        self, bounces: List[BounceEvent], match_type: str
    ) -> Dict:
        return {
            "auto_result": "UNKNOWN",
            "referee_confidence": 0.15,
            "referee_reason": "检测到的弹跳不足，无法评估回合。",
            "bounces": [be.to_dict() for be in bounces],
            "bounce_count": len(bounces),
            "court_context": "unknown",
            "last_hitter": "UNKNOWN",
            "winning_side": None,
            "is_in": None,
            "landing_point": None,
            "landing_confidence": 0.0,
            "direction_consistency": 0.0,
            "landing_margin": 0.0,
            "match_type": match_type,
            "referee_trace": {
                "decision": "insufficient-signal",
                "rule_chain": "",
                "bounce_sides": [be.side for be in bounces],
            },
        }
