import os

# === Path Configuration ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHECKPOINT_DIR = os.path.join(BASE_DIR, "checkpoints")

# Ensure model files exist
TRACKNET_PATH = os.path.join(CHECKPOINT_DIR, "TrackNet_best.pt")
INPAINTNET_PATH = os.path.join(CHECKPOINT_DIR, "InpaintNet_best.pt")
YOLO_PATH = os.path.join(CHECKPOINT_DIR, "yolov8n-pose.pt")
DB_PATH = os.path.join(BASE_DIR, "db", "chroma_store")

# Table-Tennis model paths
TT_TRACKNET_PATH = os.path.join(CHECKPOINT_DIR, "tracknetv2_midpoint_best.pt")
TT_INPAINTNET_PATH = os.path.join(CHECKPOINT_DIR, "pingpong_inpaintnet.pt")

# === Vision Parameters ===
# TrackNet training input resolution
WIDTH = 512
HEIGHT = 288
COOR_TH = 0.5  # Coordinate confidence threshold

# === Court Parameters (standard badminton court, in meters) ===
COURT_LENGTH = 13.40        # Full court length
COURT_WIDTH_DOUBLES = 6.10  # Full doubles width
COURT_WIDTH_SINGLES = 5.18  # Singles width without the side alleys
SIDE_ALLEY_WIDTH = 0.46     # Singles side alley width: (6.10 - 5.18) / 2

# === Table Parameters (standard table tennis table, in meters) ===
TABLE_LENGTH = 2.74
TABLE_WIDTH = 1.525
TABLE_NET_HEIGHT = 0.1525

# === LLM Configuration ===
LLM_API_KEY = "sk-jmejoxfvdgbngoqujxbzuxatxpxtgbzlnibjcphwioeueleg"
LLM_BASE_URL = "https://api.siliconflow.cn/v1"
LLM_MODEL_NAME = "deepseek-ai/DeepSeek-V3"
