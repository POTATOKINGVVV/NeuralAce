"""Quick diagnostic: check what TrackNet actually outputs for the test video."""
import sys
sys.path.insert(0, ".")

import numpy as np
import torch
from torch.utils.data import DataLoader

from config import TT_TRACKNET_PATH, HEIGHT, WIDTH
from core.vision.utils import generate_frames, get_model, get_ensemble_weight, predict_location
from core.vision.tracker import VideoDataset

video = sys.argv[1] if len(sys.argv) > 1 else "tt_short.mp4"
device = torch.device("cpu")

# Load model
ckpt = torch.load(TT_TRACKNET_PATH, map_location=device)
state_dict = ckpt["model_state_dict"]
in_ch = state_dict["inc.double_conv.0.weight"].shape[1]
seq_len = in_ch // 3
model = get_model("TrackNetV2", seq_len).to(device)
model.load_state_dict(state_dict)
model.eval()

# Load frames
frames, fps = generate_frames(video)
print(f"Video: {len(frames)} frames, {fps:.1f} fps, input res: {WIDTH}x{HEIGHT}")
print(f"Frame dtype: {frames[0].dtype}, shape: {frames[0].shape}, range: [{frames[0].min()}, {frames[0].max()}]")

dataset = VideoDataset(frames, seq_len, sliding_step=1, bg_frame=None)
loader = DataLoader(dataset, batch_size=16, shuffle=False)

# Run inference on first batch only
x_batch, idx_batch = next(iter(loader))
print(f"\nInput batch shape: {x_batch.shape}, dtype: {x_batch.dtype}")
print(f"Input range: [{x_batch.min():.4f}, {x_batch.max():.4f}]")

with torch.no_grad():
    y_pred = model(x_batch)

print(f"Output shape: {y_pred.shape}")
print(f"Output range: [{y_pred.min():.4f}, {y_pred.max():.4f}]")
print(f"Output mean: {y_pred.mean():.6f}, std: {y_pred.std():.6f}")

# Check a few frames
for i in range(min(3, y_pred.shape[0])):
    for j in range(y_pred.shape[1]):
        hm = y_pred[i, j].numpy() * 255
        cx, cy = predict_location(hm)
        hm_max = hm.max()
        above_127 = (hm > 127).sum()
        print(f"  batch[{i}] frame[{j}]: heatmap max={hm_max:.1f}, pixels>127={above_127}, predicted=({cx},{cy})")
