import os
import shutil
import uuid

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from core.agent.llm import CoachAgent
from core.agent.wearable_coach import WearableCoach
from core.memory.rag_engine import RAGEngine
from core.physics.engine import PhysicsEngine
from core.vision.court_detector import CourtDetector
from core.vision.pose import PoseAnalyzer
from core.vision.tracker import BallTracker
from schemas.analysis_response import MatchAnalysisResponse, RallyAnalysisResponse
from services import AnalysisService

app = FastAPI(title="NeuralAce Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

print("System Initializing...")
tracker = BallTracker()
court_detector = CourtDetector()
pose_analyzer = PoseAnalyzer()
physics = PhysicsEngine()
rag = RAGEngine()
coach = CoachAgent()
wearable_coach = WearableCoach()
analysis_service = AnalysisService(
    tracker=tracker,
    court_detector=court_detector,
    pose_analyzer=pose_analyzer,
    physics=physics,
    rag=rag,
    coach=coach,
)
print("System Ready.")

TEMP_DIR = "temp_uploads"
os.makedirs(TEMP_DIR, exist_ok=True)

ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}


def validate_match_type(match_type: str) -> str:
    if match_type not in {"singles", "doubles"}:
        raise HTTPException(status_code=400, detail="match_type 必须为 'singles' 或 'doubles'。")
    return match_type

def validate_sport_type(sport_type: str) -> str:
    if sport_type not in {"badminton", "table_tennis"}:
        raise HTTPException(status_code=400, detail="sport_type 必须为 'badminton' 或 'table_tennis'。")
    return sport_type

def validate_upload(file: UploadFile):
    suffix = os.path.splitext(file.filename or "")[1].lower()
    if suffix and suffix not in ALLOWED_VIDEO_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {suffix}")


@app.get("/")
async def root():
    return {"status": "running", "message": "NeuralAce Backend is ready!"}


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "services": {
            "tracker": "ready",
            "court_detector": "ready",
            "pose_analyzer": "ready",
            "physics": "ready",
            "rag": "ready",
            "coach": "ready",
            "wearable_coach": "ready",
        },
    }


@app.post("/analyze_rally", response_model=RallyAnalysisResponse)
async def analyze_rally(file: UploadFile = File(...),  match_type: str = Form("singles"), sport_type: str = Form("badminton")):
    
    match_type = validate_match_type(match_type)
    sport_type = validate_sport_type(sport_type)
    validate_upload(file)

    filename = f"{uuid.uuid4()}.mp4"
    filepath = os.path.join(TEMP_DIR, filename)

    with open(filepath, "wb") as output_file:
        shutil.copyfileobj(file.file, output_file)

    try:
        return analysis_service.analyze_rally(filepath, match_type, sport_type)
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))
    finally:
        if os.path.exists(filepath):
            os.remove(filepath)


@app.post("/analyze_match", response_model=MatchAnalysisResponse)
async def analyze_match(file: UploadFile = File(...), match_type: str = Form("singles"), sport_type: str = Form("badminton")):
    match_type = validate_match_type(match_type)
    sport_type = validate_sport_type(sport_type)
    validate_upload(file)

    filename = f"match_{uuid.uuid4()}.mp4"
    filepath = os.path.join(TEMP_DIR, filename)

    with open(filepath, "wb") as output_file:
        shutil.copyfileobj(file.file, output_file)

    try:
        return analysis_service.analyze_match(filepath, match_type, sport_type)
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))
    finally:
        if os.path.exists(filepath):
            os.remove(filepath)


@app.post("/feedback")
async def feedback(tactic_id: str = Form(...), result: str = Form(...)):
    reward = physics.calculate_reward(result)
    rag.update_policy(tactic_id, reward, context={"auto_result": result})
    return {"status": "ok", "reward": reward}


# ── WebSocket: Real-time Wearable Coaching ──────────────────────────────

@app.websocket("/ws/wearable")
async def wearable_stream(websocket: WebSocket):
    await websocket.accept()
    wearable_coach.reset()
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "imu")

            if msg_type == "heartRate":
                alerts = wearable_coach.evaluate({
                    "heartRate": data.get("bpm", 0),
                    "timestamp": data.get("timestamp", 0),
                    "accelX": 0, "accelY": 0, "accelZ": 0,
                })
            else:
                alerts = wearable_coach.evaluate(data)

            if alerts:
                await websocket.send_json({
                    "alerts": alerts,
                    "physical_state": wearable_coach.get_physical_state(),
                })
    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"error": str(e)})
        except Exception:
            pass


@app.get("/wearable/state")
async def wearable_state():
    return wearable_coach.get_physical_state()


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)


