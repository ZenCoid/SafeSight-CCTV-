"""
SafeSight CCTV - Multi-Camera Main Application
FastAPI server with support for multiple cameras via NVR/DVR channels.
Single-camera view with browser Fullscreen API for big screen.
"""
import os
import time
import cv2
import numpy as np
import uvicorn
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from config import Config, CameraConfig
from camera import ThreadedCamera
from detector import YOLODetector
from database import ViolationDB

# Force TCP for RTSP — MUST be before any cv2.VideoCapture()
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"


# ─── Lifespan ──────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global detector, database

    print("\n" + "=" * 55)
    print("   SafeSight CCTV - Multi-Camera System v3.0")
    print("=" * 55)

    os.makedirs(Config.SNAPSHOT_DIR, exist_ok=True)

    cam_list = Config.load_cameras()
    if not cam_list:
        print("[WARNING] No cameras found in cameras.json!")

    # Start all camera grabber threads (background RTSP connections)
    # Only ONE MJPEG stream is served at a time to the browser
    for cam_conf in cam_list:
        camera_configs[cam_conf.id] = cam_conf
        rtsp_url = build_rtsp_url(cam_conf, subtype=1)
        cam = ThreadedCamera(
            camera_id=cam_conf.id,
            camera_name=cam_conf.name,
            rtsp_url=rtsp_url,
        )
        cameras[cam_conf.id] = cam
        detection_enabled[cam_conf.id] = True

        if cam.start():
            print(f"  [OK] {cam_conf.name} (sub) - Channel {cam_conf.channel}")
        else:
            print(f"  [--] {cam_conf.name} (sub) - Failed (will auto-retry)")

    print("  [..] View: Single camera selector + Browser Fullscreen API")

    det = get_detector()
    if not det.load_model():
        print("[WARNING] Model failed to load!")

    get_database()

    print("=" * 55)
    print(f"   Dashboard: http://localhost:{Config.SERVER_PORT}")
    print(f"   Cameras: {len(cameras)} | Stream: /stream/<id>")
    print("=" * 55 + "\n")

    yield

    print("[Shutdown] Cleaning up...")
    for cam in cameras.values():
        cam.stop()
    if database:
        database.close()


# ─── App Setup ──────────────────────────────────────────────────

app = FastAPI(title="SafeSight CCTV", version="3.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# ─── Global Instances ──────────────────────────────────────────

cameras: dict[str, ThreadedCamera] = {}
detector: YOLODetector = None
database: ViolationDB = None
camera_configs: dict[str, CameraConfig] = {}
detection_enabled: dict[str, bool] = {}


def get_detector() -> YOLODetector:
    global detector
    if detector is None:
        detector = YOLODetector(
            model_path=Config.MODEL_PATH,
            confidence=Config.CONFIDENCE_THRESHOLD,
        )
    return detector


def get_database() -> ViolationDB:
    global database
    if database is None:
        database = ViolationDB()
    return database


def build_rtsp_url(cam_conf: CameraConfig, subtype: int) -> str:
    encoded_pwd = quote(cam_conf.password, safe='')
    return (
        f"rtsp://{cam_conf.username}:{encoded_pwd}@{cam_conf.ip}:{cam_conf.port}"
        f"/cam/realmonitor?channel={cam_conf.channel}&subtype={subtype}"
    )


# ─── Routes ─────────────────────────────────────────────────────

# SPA catch-all
@app.get("/", response_class=HTMLResponse)
@app.get("/violations", response_class=HTMLResponse)
@app.get("/cameras-page", response_class=HTMLResponse)
@app.get("/settings", response_class=HTMLResponse)
@app.get("/timeline", response_class=HTMLResponse)
async def dashboard():
    index_path = static_dir / "index.html"
    return HTMLResponse(index_path.read_text(encoding="utf-8"))


@app.get("/api/cameras")
async def camera_list():
    result = []
    for cc in Config.cameras:
        status = cameras.get(cc.id)
        info = {
            "id": cc.id,
            "name": cc.name,
            "ip": cc.ip,
            "channel": cc.channel,
            "connected": status.connected if status else False,
            "fps": status.get_status()["fps"] if status else 0,
            "resolution": status.get_status()["resolution"] if status else (0, 0),
            "detection_enabled": detection_enabled.get(cc.id, True),
        }
        result.append(info)
    return {"cameras": result}


@app.get("/stream/{camera_id}")
async def video_stream(camera_id: str):
    """MJPEG video stream — serves ONE camera at a time."""
    cam = cameras.get(camera_id)
    if not cam:
        return {"error": f"Camera '{camera_id}' not found"}

    det = get_detector()
    interval = 1.0 / Config.STREAM_FPS

    def generate():
        while True:
            frame_start = time.time()

            frame = cam.get_frame()
            if frame is None:
                no_sig = create_no_signal_frame(camera_id)
                _, jpeg = cv2.imencode(".jpg", no_sig, [cv2.IMWRITE_JPEG_QUALITY, 70])
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n"
                time.sleep(0.5)
                continue

            if detection_enabled.get(camera_id, True):
                annotated, _ = det.detect(camera_id, frame)
            else:
                annotated = frame

            _, jpeg = cv2.imencode(".jpg", annotated, [
                cv2.IMWRITE_JPEG_QUALITY, Config.JPEG_QUALITY
            ])
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n"

            elapsed = time.time() - frame_start
            sleep_time = interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.get("/api/status")
async def get_status():
    det = get_detector()
    return {
        "cameras": {cid: cam.get_status() for cid, cam in cameras.items()},
        "detector": det.get_stats(),
        "detection_enabled": detection_enabled,
        "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


@app.get("/api/stats")
async def get_stats():
    det = get_detector()
    db = get_database()
    return {
        "detection": det.get_stats(),
        "violations": db.get_stats(),
        "cameras": len(cameras),
        "cameras_online": sum(1 for c in cameras.values() if c.connected),
    }


@app.get("/api/violations")
async def get_violations(limit: int = 50, offset: int = 0, hours: int = 24, camera_id: str = None):
    db = get_database()
    violations = db.get_violations(limit=limit, offset=offset, hours=hours, camera_id=camera_id)
    for v in violations:
        if v.get("snapshot_path"):
            v["snapshot_url"] = f"/snapshots/{os.path.basename(v['snapshot_path'])}"
    return {"violations": violations, "count": len(violations)}


@app.post("/api/detection/toggle/{camera_id}")
async def toggle_detection(camera_id: str):
    if camera_id not in cameras:
        return {"error": "Camera not found"}, 404
    detection_enabled[camera_id] = not detection_enabled.get(camera_id, True)
    return {"camera_id": camera_id, "enabled": detection_enabled[camera_id]}


@app.post("/api/camera/reconnect/{camera_id}")
async def reconnect_camera(camera_id: str):
    cam = cameras.get(camera_id)
    if not cam:
        return {"error": "Camera not found"}, 404
    success = cam.connect()
    return {"camera_id": camera_id, "success": success}


@app.post("/api/camera/reconnect_all")
async def reconnect_all():
    results = {}
    for cid, cam in cameras.items():
        results[cid] = cam.connect()
    return results


# ─── WebSocket ─────────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self.connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.connections:
            self.connections.remove(ws)

    async def broadcast(self, message: dict):
        dead = []
        for ws in self.connections:
            try:
                await ws.send_json(message)
            except:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


ws_manager = ConnectionManager()


@app.websocket("/ws/alerts")
async def websocket_alerts(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        while True:
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)


# ─── Helper ─────────────────────────────────────────────────────

def create_no_signal_frame(camera_name: str):
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    cv2.putText(frame, "Connecting...", (500, 340), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 2)
    cv2.putText(frame, camera_name, (500, 380), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (150, 150, 150), 1)
    return frame


# ─── Run ────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\nStarting SafeSight CCTV Multi-Camera Server...\n")
    uvicorn.run(
        "main:app",
        host=Config.SERVER_HOST,
        port=Config.SERVER_PORT,
        log_level="info",
        access_log=False,
    )