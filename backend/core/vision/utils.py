import cv2
import numpy as np
import scipy.signal
import torch

from config import HEIGHT, WIDTH


def get_ensemble_weight(seq_len, mode='weight'):
    """
    Build the temporal fusion weight vector.
    In `weight` mode, a Gaussian window emphasizes the center frames.
    """
    if mode == 'nonoverlap':
        return torch.ones(seq_len)
    if mode == 'average':
        return torch.ones(seq_len) / seq_len
    if mode == 'weight':
        # Use a Gaussian curve with std = seq_len / 3 to cover the main region.
        gaussian_weights = scipy.signal.windows.gaussian(seq_len, std=seq_len / 3)
        return torch.from_numpy(gaussian_weights).float()
    raise ValueError('Invalid evaluation mode')


def generate_frames(video_path):
    """Read the video and resize frames to the model input resolution."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise IOError(f"Cannot open video: {video_path}")

    frames = []
    fps = cap.get(cv2.CAP_PROP_FPS)

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        # Force resize to TrackNet's expected 512x288 input.
        frame_resized = cv2.resize(frame, (WIDTH, HEIGHT))
        frames.append(frame_resized)

    cap.release()
    return frames, fps


def predict_location(heatmap):
    """Extract the center of the largest connected component from a heatmap."""
    heatmap = np.array(heatmap, dtype=np.uint8)
    _, thresh = cv2.threshold(heatmap, 127, 255, 0)
    contours, _ = cv2.findContours(thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    if len(contours) > 0:
        contour = max(contours, key=cv2.contourArea)
        x, y, w, h = cv2.boundingRect(contour)
        return (int(x + w / 2), int(y + h / 2))
    return (0, 0)


def generate_inpaint_mask(pred_dict):
    """
    Build the mask required by InpaintNet.
    If Visibility == 0 or the coordinate is (0, 0), mark it as missing.
    """
    frames = pred_dict['Frame']
    x_list = pred_dict['X']
    y_list = pred_dict['Y']
    vis_list = pred_dict['Visibility']

    mask = []
    for i in range(len(frames)):
        if vis_list[i] == 0 or (x_list[i] == 0 and y_list[i] == 0):
            mask.append(1.0)
        else:
            mask.append(0.0)
    return np.array(mask)


def algorithmic_inpaint(
    pred_dict: dict,
    max_gap: int = 30,
    max_extrap: int = 3,
    speed_cap_px: float = 200.0,
) -> list:
    """Lightweight trajectory completion via cubic-spline interpolation.

    Replaces InpaintNet when no weights are available.  Produces a visually
    plausible (though not pixel-perfect) trajectory by:

    1. Collecting all observed (visible) frame indices and coordinates.
    2. Fitting a cubic spline through observed X and Y independently.
    3. Filling interior gaps up to *max_gap* frames.
    4. Optionally extrapolating up to *max_extrap* frames at boundaries.
    5. Rejecting implausible fills whose per-frame speed exceeds
       *speed_cap_px* pixels/frame.

    Returns a list of (x, y) int tuples with the same length as the input.
    """
    xs = np.array(pred_dict["X"], dtype=np.float64)
    ys = np.array(pred_dict["Y"], dtype=np.float64)
    vis = np.array(pred_dict["Visibility"], dtype=np.int32)
    n = len(xs)

    result = list(zip(xs.astype(int).tolist(), ys.astype(int).tolist()))
    observed_idx = np.where((vis > 0) & (xs > 0) & (ys > 0))[0]

    if len(observed_idx) < 4:
        # Too few anchors – fall back to raw trajectory.
        return result

    obs_x = xs[observed_idx]
    obs_y = ys[observed_idx]

    # --- Cubic spline fit --------------------------------------------------
    try:
        from scipy.interpolate import CubicSpline
        cs_x = CubicSpline(observed_idx, obs_x, bc_type="natural")
        cs_y = CubicSpline(observed_idx, obs_y, bc_type="natural")
    except Exception:
        # scipy unavailable or fitting failed – return raw.
        return result

    first_obs = int(observed_idx[0])
    last_obs = int(observed_idx[-1])

    # --- Fill interior gaps ------------------------------------------------
    i = 0
    while i < n:
        if vis[i] > 0 and xs[i] > 0:
            i += 1
            continue
        gap_start = i
        while i < n and (vis[i] == 0 or xs[i] <= 0):
            i += 1
        gap_end = i  # exclusive

        # Only interpolate interior gaps within observed range and ≤ max_gap.
        if gap_start >= first_obs and gap_end <= last_obs + 1 and (gap_end - gap_start) <= max_gap:
            for fi in range(gap_start, gap_end):
                nx_ = float(cs_x(fi))
                ny_ = float(cs_y(fi))
                # Plausibility: check speed relative to nearest observed frame
                _ok = True
                for anchor in (gap_start - 1, gap_end):
                    if 0 <= anchor < n and vis[anchor] > 0:
                        dx = nx_ - float(xs[anchor])
                        dy = ny_ - float(ys[anchor])
                        dist = (dx * dx + dy * dy) ** 0.5
                        dt = abs(fi - anchor) or 1
                        if dist / dt > speed_cap_px:
                            _ok = False
                            break
                if _ok and nx_ > 0 and ny_ > 0:
                    result[fi] = (max(0, int(round(nx_))), max(0, int(round(ny_))))

    # --- Boundary extrapolation (limited) ----------------------------------
    for fi in range(max(0, first_obs - max_extrap), first_obs):
        nx_ = float(cs_x(fi))
        ny_ = float(cs_y(fi))
        if nx_ > 0 and ny_ > 0:
            result[fi] = (int(round(nx_)), int(round(ny_)))

    for fi in range(last_obs + 1, min(n, last_obs + 1 + max_extrap)):
        nx_ = float(cs_x(fi))
        ny_ = float(cs_y(fi))
        if nx_ > 0 and ny_ > 0:
            result[fi] = (int(round(nx_)), int(round(ny_)))

    return result


def get_model(model_name, seq_len=None, bg_mode=None):
    # Import lazily to avoid circular imports.
    from core.vision.models import InpaintNet, TrackNet, TrackNetV2

    if model_name == 'TrackNet':
        in_dim = seq_len * 3
        if bg_mode:
            # seq_len * 3 + 3 = 27 channels (8 RGB frames + 1 RGB background frame)
            in_dim = seq_len * 3 + 3
        out_dim = seq_len
        return TrackNet(in_dim, out_dim)
    if model_name == 'TrackNetV2':
        in_dim = seq_len * 3
        out_dim = seq_len
        return TrackNetV2(in_dim, out_dim)
    if model_name == 'InpaintNet':
        return InpaintNet()
    raise ValueError(f"Unsupported model name: {model_name}")
