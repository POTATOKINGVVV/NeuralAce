# core/vision/table_tennis_tracker.py

from __future__ import annotations

import numpy as np
import torch
from torch.utils.data import DataLoader
from tqdm import tqdm

from config import COOR_TH, HEIGHT, TT_INPAINTNET_PATH, TT_TRACKNET_PATH, WIDTH
from core.vision.tracker import CoordinateDataset, VideoDataset
from core.vision.trajectory_postprocess import TrajectoryPostProcessor
from core.vision.utils import (
    algorithmic_inpaint,
    generate_frames,
    generate_inpaint_mask,
    get_ensemble_weight,
    get_model,
    predict_location,
)


class TableTennisTracker:
    """Ball tracker for table tennis using TrackNetV2.

    Loads table-tennis-specific pre-trained weights from
    ``tracknetv2_midpoint_best.pt`` (checkpoint with ``model_state_dict``).
    Optionally loads InpaintNet for trajectory refinement.

    The public interface (``infer`` / ``infer_detailed``) is identical to
    :class:`~core.vision.tracker.BallTracker` so that the service layer can
    consume both interchangeably.
    """

    def __init__(self):
        self.device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
        self.postprocessor = TrajectoryPostProcessor()
        self.last_diagnostics: dict = {}

        # --- TrackNetV2 (table-tennis weights) ---------------------------------
        tn_ckpt = torch.load(TT_TRACKNET_PATH, map_location=self.device)

        # Detect checkpoint format: new format uses 'model_state_dict',
        # legacy format uses 'param_dict' + 'model'.
        if "model_state_dict" in tn_ckpt:
            state_dict = tn_ckpt["model_state_dict"]
            # Infer seq_len from the first conv layer input channels:
            # inc.double_conv.0.weight shape is (64, in_channels, 3, 3)
            in_channels = state_dict["inc.double_conv.0.weight"].shape[1]
            self.tn_seq_len = in_channels // 3
            self.bg_mode = None

            self.tracknet = get_model("TrackNetV2", self.tn_seq_len).to(self.device)
            self.tracknet.load_state_dict(state_dict)
            print(f"[TT-Tracker] Loaded TrackNetV2 (seq_len={self.tn_seq_len}) from new-format checkpoint")
        else:
            # Legacy format (param_dict + model)
            self.tn_seq_len = tn_ckpt["param_dict"]["seq_len"]
            self.bg_mode = tn_ckpt["param_dict"].get("bg_mode", None)
            self.tracknet = get_model("TrackNet", self.tn_seq_len, self.bg_mode).to(self.device)
            self.tracknet.load_state_dict(tn_ckpt["model"])
            print(f"[TT-Tracker] Loaded TrackNet (seq_len={self.tn_seq_len}) from legacy checkpoint")

        self.tracknet.eval()

        # --- InpaintNet (optional) ---------------------------------------------
        self.inpaintnet = None
        self.in_seq_len = self.tn_seq_len  # fallback
        if TT_INPAINTNET_PATH:
            import os
            if os.path.isfile(TT_INPAINTNET_PATH):
                try:
                    in_ckpt = torch.load(TT_INPAINTNET_PATH, map_location=self.device)
                    if "param_dict" in in_ckpt:
                        self.in_seq_len = in_ckpt["param_dict"]["seq_len"]
                    self.inpaintnet = get_model("InpaintNet").to(self.device)
                    sd_key = "model_state_dict" if "model_state_dict" in in_ckpt else "model"
                    self.inpaintnet.load_state_dict(in_ckpt[sd_key])
                    self.inpaintnet.eval()
                    print("[TT-Tracker] InpaintNet loaded successfully")
                except Exception as error:
                    print(f"[TT-Tracker] Warning: Failed to load InpaintNet: {error}")
            else:
                print(f"[TT-Tracker] InpaintNet weight not found, skipping trajectory refinement")

    # ------------------------------------------------------------------
    # Public API – mirrors BallTracker exactly
    # ------------------------------------------------------------------

    def infer(self, video_path: str):
        trajectory, fps, diagnostics = self.infer_detailed(video_path)
        self.last_diagnostics = diagnostics
        return trajectory, fps

    def infer_detailed(self, video_path: str):
        frames, fps = generate_frames(video_path)
        video_len = len(frames)

        bg_frame = None
        if self.bg_mode:
            if len(frames) > 50:
                indices = np.linspace(0, len(frames) - 1, 50, dtype=int)
                sample_frames = [frames[i] for i in indices]
                bg_frame = np.median(sample_frames, axis=0).astype(np.uint8)
            else:
                bg_frame = np.median(frames, axis=0).astype(np.uint8)

        dataset = VideoDataset(frames, self.tn_seq_len, sliding_step=1, bg_frame=bg_frame, normalize=False)
        loader = DataLoader(dataset, batch_size=16, shuffle=False)

        heatmap_accum = torch.zeros((video_len, HEIGHT, WIDTH), device="cpu")
        count_accum = torch.zeros((video_len, 1, 1), device="cpu")
        weight = get_ensemble_weight(self.tn_seq_len, mode="weight").view(self.tn_seq_len, 1, 1)

        with torch.no_grad():
            for x, frame_indices in tqdm(loader, desc="TT-TrackNet"):
                x = x.to(self.device)
                y_pred = self.tracknet(x).detach().cpu()

                for batch_index in range(y_pred.shape[0]):
                    idx = frame_indices[batch_index]
                    heatmap_accum[idx] += y_pred[batch_index] * weight
                    count_accum[idx] += weight

        avg_heatmap = heatmap_accum / (count_accum + 1e-6)

        pred_dict: dict = {"Frame": [], "X": [], "Y": [], "Visibility": []}
        for frame_index in range(video_len):
            heatmap = avg_heatmap[frame_index].numpy() * 255
            cx, cy = predict_location(heatmap)
            pred_dict["Frame"].append(frame_index)
            pred_dict["X"].append(cx)
            pred_dict["Y"].append(cy)
            pred_dict["Visibility"].append(1 if (cx > 0 or cy > 0) else 0)

        raw_traj = list(zip(pred_dict["X"], pred_dict["Y"]))

        if self.inpaintnet:
            mask = generate_inpaint_mask(pred_dict)
            coords = np.stack([pred_dict["X"], pred_dict["Y"]], axis=1)

            coord_ds = CoordinateDataset(coords, mask, self.in_seq_len)
            coord_loader = DataLoader(coord_ds, batch_size=64, shuffle=False)

            coord_accum = torch.zeros((video_len, 2), device="cpu")
            coord_count = torch.zeros((video_len, 1), device="cpu")
            in_weight = get_ensemble_weight(self.in_seq_len, mode="weight").view(self.in_seq_len, 1)

            with torch.no_grad():
                for c_seq, m_seq, c_indices in tqdm(coord_loader, desc="TT-InpaintNet"):
                    c_seq = c_seq.float().to(self.device)
                    m_seq = m_seq.float().to(self.device).unsqueeze(-1)
                    c_pred = self.inpaintnet(c_seq, m_seq).detach().cpu()

                    for batch_index in range(c_pred.shape[0]):
                        idx = c_indices[batch_index]
                        valid_mask = idx < video_len
                        valid_idx = idx[valid_mask]
                        if len(valid_idx) > 0:
                            valid_pred = c_pred[batch_index][valid_mask]
                            valid_weight = in_weight[valid_mask]
                            coord_accum[valid_idx] += valid_pred * valid_weight
                            coord_count[valid_idx] += valid_weight

            refined_coords = (coord_accum / (coord_count + 1e-6)).numpy()
            final_traj = []
            for frame_index in range(video_len):
                if mask[frame_index] > 0.5:
                    cx, cy = refined_coords[frame_index]
                    if cx < COOR_TH or cy < COOR_TH:
                        cx, cy = 0, 0
                else:
                    cx, cy = coords[frame_index]
                final_traj.append((int(cx), int(cy)))
        else:
            # No InpaintNet – use lightweight cubic-spline inpainting
            final_traj = algorithmic_inpaint(pred_dict)

        processed = self.postprocessor.postprocess(final_traj)
        diagnostics = {
            "video_frames": video_len,
            "raw_visible_frames": int(sum(1 for x, y in raw_traj if x > 0 and y > 0)),
            **processed["diagnostics"],
        }
        self.last_diagnostics = diagnostics
        return processed["trajectory"], fps, diagnostics
