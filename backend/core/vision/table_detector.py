# core/vision/table_detector.py

from __future__ import annotations

import logging
from typing import Dict, Optional, Tuple

import cv2
import numpy as np


logger = logging.getLogger(__name__)

# Fallback HSV ranges tried when the primary range yields no result.
_FALLBACK_HSV_RANGES = [
    # Green tables (common in competition)
    (np.array([35, 40, 40], dtype=np.uint8), np.array([85, 255, 255], dtype=np.uint8)),
]


class TableDetector:
    """使用纯 OpenCV 进行乒乓球桌检测并输出几何信息。"""

    def __init__(
        self,
        lower_hsv: Tuple[int, int, int] = (90, 50, 50),
        upper_hsv: Tuple[int, int, int] = (130, 255, 255),
        min_contour_area_ratio: float = 0.02,
        morph_kernel_size: int = 5,
    ):
        self.lower_hsv = np.array(lower_hsv, dtype=np.uint8)
        self.upper_hsv = np.array(upper_hsv, dtype=np.uint8)
        self.min_contour_area_ratio = min_contour_area_ratio

        kernel_size = max(3, int(morph_kernel_size))
        if kernel_size % 2 == 0:
            kernel_size += 1
        self.kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))

        # ===== State =====
        self.prev_corners: Optional[np.ndarray] = None
        self.max_step: float = 5.0

        # Populated after every ``detect`` call.
        self.last_net_line: Optional[Tuple[Tuple[float, float], Tuple[float, float]]] = None
        self.last_detection_meta: Dict = {}

    # ------------------------------------------------------------------
    # Core public API
    # ------------------------------------------------------------------

    def detect(self, frame: np.ndarray) -> np.ndarray:
        """返回桌角点 ``np.ndarray(4, 2)``，顺序为 TL, TR, BR, BL。"""
        if frame is None or frame.size == 0:
            logger.warning("桌面检测失败：输入帧为空，使用默认回退角点。")
            corners = self._get_fallback_corners(1280, 720)
            self.last_detection_meta = {"source": "fallback_empty_frame", "confidence": 0.0}
        else:
            h_img, w_img = frame.shape[:2]
            corners = self._detect_table_corners(frame)

            if corners is None:
                logger.warning("桌面检测失败：未找到有效桌面轮廓，使用默认回退角点。")
                corners = self._get_fallback_corners(w_img, h_img)
                self.last_detection_meta = {"source": "fallback_no_contour", "confidence": 0.0}
            else:
                self.last_detection_meta = {"source": "opencv_hsv_contour", "confidence": 1.0}

        corners = self._smooth_corners(corners)
        self.last_net_line = self._compute_net_line(corners)
        return corners

    def detect_with_net(self, frame: np.ndarray) -> Dict:
        """Return corners and net-line geometry in a single call.

        Useful when the strategy layer needs both in one pass.  The dict has
        the same shape expected by ``PhysicsEngine.update_homography`` (via the
        ``corners`` key) plus an additional ``net_line`` key.
        """
        corners = self.detect(frame)
        return {
            "corners": corners,
            "net_line": self.last_net_line,
            "meta": self.last_detection_meta,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _detect_table_corners(self, frame: np.ndarray) -> Optional[np.ndarray]:
        h_img, w_img = frame.shape[:2]
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        min_area = float(h_img * w_img) * float(self.min_contour_area_ratio)

        # Build the list of HSV ranges to try: primary first, then fallbacks.
        ranges_to_try = [(self.lower_hsv, self.upper_hsv)] + list(_FALLBACK_HSV_RANGES)

        for lower, upper in ranges_to_try:
            result = self._try_hsv_range(hsv, lower, upper, min_area)
            if result is not None:
                logger.info("桌面检测成功：已输出 4 个角点 (HSV %s–%s)。", lower.tolist(), upper.tolist())
                return result

        logger.info("桌面检测：所有 HSV 范围均未找到有效轮廓。")
        return None

    def _try_hsv_range(
        self,
        hsv: np.ndarray,
        lower: np.ndarray,
        upper: np.ndarray,
        min_area: float,
    ) -> Optional[np.ndarray]:
        """Attempt detection with a single HSV range, return ordered corners or None."""
        mask = cv2.inRange(hsv, lower, upper)
        mask = cv2.erode(mask, self.kernel, iterations=1)
        mask = cv2.dilate(mask, self.kernel, iterations=2)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, self.kernel, iterations=2)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None

        largest = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(largest)
        if area < min_area:
            return None

        perimeter = cv2.arcLength(largest, True)
        quad = self._approx_to_quad(largest, perimeter)
        if quad is None:
            rect = cv2.minAreaRect(largest)
            quad = cv2.boxPoints(rect).astype(np.float32)

        return self._order_corners(quad)

    @staticmethod
    def _approx_to_quad(contour: np.ndarray, perimeter: float) -> Optional[np.ndarray]:
        """尝试不同 epsilon，让 approxPolyDP 输出稳定四边形。"""
        for factor in np.linspace(0.01, 0.08, 16):
            epsilon = float(factor) * perimeter
            approx = cv2.approxPolyDP(contour, epsilon, True)
            if len(approx) == 4:
                return approx.reshape(4, 2).astype(np.float32)
        return None

    @staticmethod
    def _order_corners(pts: np.ndarray) -> np.ndarray:
        """Order an unordered set of 4 points as TL, TR, BR, BL (clockwise).

        Sorting logic:
        1. Sum of coordinates (x+y): smallest → TL, largest → BR.
        2. Difference (y-x): smallest → TR, largest → BL.
        """
        ordered = np.zeros((4, 2), dtype=np.float32)
        s = pts.sum(axis=1)
        d = np.diff(pts, axis=1).ravel()
        ordered[0] = pts[np.argmin(s)]   # TL
        ordered[2] = pts[np.argmax(s)]   # BR
        ordered[1] = pts[np.argmin(d)]   # TR
        ordered[3] = pts[np.argmax(d)]   # BL
        return ordered

    def _smooth_corners(self, corners: np.ndarray) -> np.ndarray:
        """Temporally smooth corners to prevent jitter between frames."""
        if self.prev_corners is None:
            self.prev_corners = corners
            return corners

        delta = corners - self.prev_corners
        dist = np.linalg.norm(delta, axis=1, keepdims=True)
        dist = np.maximum(dist, 1e-6)
        scale = np.minimum(1.0, self.max_step / dist)
        corners = self.prev_corners + delta * scale
        self.prev_corners = corners
        return corners

    @staticmethod
    def _compute_net_line(
        corners: np.ndarray,
    ) -> Tuple[Tuple[float, float], Tuple[float, float]]:
        """根据四角点计算球网线（左右边中点连线）。"""
        tl, tr, br, bl = corners[0], corners[1], corners[2], corners[3]
        mid_left = ((tl[0] + bl[0]) / 2.0, (tl[1] + bl[1]) / 2.0)
        mid_right = ((tr[0] + br[0]) / 2.0, (tr[1] + br[1]) / 2.0)
        return (mid_left, mid_right)

    @staticmethod
    def _get_fallback_corners(w: int, h: int) -> np.ndarray:
        """Proportional fallback when detection fails — mirrors CourtDetector."""
        return np.array([
            [w * 0.2, h * 0.3],
            [w * 0.8, h * 0.3],
            [w * 0.9, h * 0.9],
            [w * 0.1, h * 0.9],
        ], dtype=np.float32)
