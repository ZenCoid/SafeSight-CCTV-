"""
SafeSight CCTV - Main Application

FastAPI application with multi-camera support, YOLO detection,
MJPEG streaming, violation alerts, and real-time WebSocket notifications.

Improvements over original main.py:
  - Pydantic Settings for type-safe configuration
  - Structured JSON logging (not print statements)
  - Global exception handlers returning proper JSON errors
  - Violation logic separated into dedicated classes
  - Cleaner lifespan with proper service initialization
  - All routes in dedicated modules
  - All original API response formats preserved (frontend compatible)

Routes preserved for frontend compatibility:
  GET  /                    — SPA dashboard (index.html)
  GET  /violations          — SPA violations page
  GET  /cameras-page        — SPA cameras page
  GET  /settings            — SPA settings page
  GET  /timeline            — SPA timeline page
  GET  /api/cameras         — Camera list
  GET  /stream/webcam       — Webcam MJPEG stream
  GET  /stream/{camera_id}  — Camera MJPEG stream
  GET  /api/status          — System status
  GET  /api/stats           — Aggregate stats
  GET  /api/violations      — Violation history
  POST /api/violations/send_test  — Test alert email
  POST /api/detection/toggle/{id} — Toggle detection
  POST /api/camera/reconnect/{id} — Reconnect camera
  POST /api/camera/reconnect_all  — Reconnect all
  WS   /ws/alerts           — Real-time alert push
"""

import os
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from contextlib import asynccontextmanager
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings

# ═══════════════════════════════════════════════════════════════════
# Structured JSON Logging
# ═══════════════════════════════════════════════════════════════════
# Load .env for LOG_LEVEL before creating Settings
from dotenv import load_dotenv
load_dotenv()

_log_level = os.getenv("LOG_LEVEL", "INFO").upper()
log_format = (
    '{"time":"%(asctime)s","level":"%(levelname)s",'
    '"name":"%(name)s","message":"%(message)s"}'
)
logging.basicConfig(
    level=getattr(logging, _log_level, logging.INFO),
    format=log_format,
    stream=sys.stdout,
)
logger = logging.getLogger("safesight")


# ═══════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════
config = Settings()
config.load_cameras()


# ═══════════════════════════════════════════════════════════════════
# Lifespan (Startup / Shutdown)
# ═══════════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle.

    Startup:
        1. Initialize database
        2. Initialize alert service
        3. Initialize storage service
        4. Load YOLO detector
        5. Start camera threads
        6. Wire violation callback

    Shutdown:
        1. Stop all cameras
        2. Close database
    """
    global detector, database

    logger.info("=" * 55)
    logger.info("  SafeSight CCTV - Multi-Camera System v4.0")
    logger.info("=" * 55)

    # 1. Database
    from app.db.database import ViolationDB
    database = ViolationDB(config)

    # 2. Alert service
    from app.services.alert_service import AlertService
    alert_service = AlertService(config)

    # 3. Storage service
    from app.services.storage_service import StorageService
    storage_service = StorageService(config)

    # 4. Violation tracker
    from app.core.violation import ViolationTracker
    violation_tracker = ViolationTracker(config)

    # 5. Detector
    from app.core.detector import YOLODetector
    detector = YOLODetector(config, violation_tracker)

    # Wire violation callback: snapshot + DB + email + WebSocket
    def on_violation(camera_id, frame, detections, max_conf):
        """Called when ViolationTracker fires an alert."""
        # Save snapshot
        snapshot_path = storage_service.save_snapshot(
            camera_id=camera_id,
            frame=frame,
            detections=detections,
        )

        # Get camera info for DB
        cam_name = str(camera_id)
        cam_ip = ""
        cam_conf = next(
            (c for c in config.cameras if c.id == camera_id), None
        )
        if cam_conf:
            cam_name = cam_conf.name
            cam_ip = cam_conf.ip

        # Log to database
        database.log_violation(
            detection_type="no_helmet",
            confidence=max_conf,
            camera_id=str(camera_id),
            camera_name=cam_name,
            camera_ip=cam_ip,
            snapshot_path=snapshot_path,
        )

        # Send email alert
        alert_service.send_violation_alert(
            camera_name=cam_name,
            detection_type="no_helmet",
            confidence=max_conf,
            snapshot_path=snapshot_path,
        )

        # Push WebSocket notification to frontend
        from app.websocket.alerts import ws_manager
        ws_manager.broadcast_sync({
            "type": "violation",
            "camera_id": camera_id,
            "camera_name": cam_name,
            "detection_type": "no_helmet",
            "confidence": max_conf,
            "timestamp": datetime.now().isoformat(),
        })

    detector.set_violation_callback(on_violation)

    if not detector.load_model():
        logger.warning("Model failed to load — running without detection")

    # 6. Start cameras
    cameras = {}
    detection_enabled = {}

    if not config.cameras:
        logger.warning("No cameras found in cameras.json!")

    for cam_conf in config.cameras:
        from app.core.camera import ThreadedCamera
        rtsp_url = cam_conf.get_rtsp_url(subtype_override=config.RTSP_SUBTYPE)
        cam = ThreadedCamera(
            camera_id=cam_conf.id,
            camera_name=cam_conf.name,
            rtsp_url=rtsp_url,
            config=config,
        )
        cameras[cam_conf.id] = cam
        detection_enabled[cam_conf.id] = True

        stream_label = "main" if config.RTSP_SUBTYPE == 0 else "sub"
        if cam.start():
            logger.info(
                "  [OK] {} ({}) - Channel {}",
                cam_conf.name, stream_label, cam_conf.channel,
            )
        else:
            logger.warning(
                "  [--] {} ({}) - Failed (will auto-retry)",
                cam_conf.name, stream_label,
            )

    # Store on app state for route access
    app.state.config = config
    app.state.cameras = cameras
    app.state.detection_enabled = detection_enabled
    app.state.detector = detector
    app.state.database = database
    app.state.alert_service = alert_service
    app.state.storage_service = storage_service
    app.state.violation_tracker = violation_tracker

    logger.info("  Dashboard: http://localhost:{}", config.SERVER_PORT)
    logger.info("  Cameras: {} | Stream: /stream/<id>", len(cameras))
    logger.info("  Webcam:  /stream/webcam")
    logger.info("=" * 55)

    yield

    # ── Shutdown ──
    logger.info("Shutting down...")
    for cam in cameras.values():
        cam.stop()
    database.close()
    logger.info("SafeSight stopped cleanly")


# ═══════════════════════════════════════════════════════════════════
# FastAPI App
# ═══════════════════════════════════════════════════════════════════

app = FastAPI(title="SafeSight CCTV", version="4.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════════════════
# Global Exception Handlers
# ═══════════════════════════════════════════════════════════════════

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch all unhandled exceptions — return proper JSON error."""
    logger.error(
        "Unhandled exception on {} {}: {}",
        request.method, request.url.path, str(exc),
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)},
    )


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    """Handle validation errors with 400 status."""
    return JSONResponse(
        status_code=400,
        content={"error": "Bad request", "detail": str(exc)},
    )


# ═══════════════════════════════════════════════════════════════════
# Static Files
# ═══════════════════════════════════════════════════════════════════

static_dir = Path(__file__).parent.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

snapshot_dir = Path(__file__).parent.parent / config.SNAPSHOT_DIR
snapshot_dir.mkdir(parents=True, exist_ok=True)
app.mount("/snapshots", StaticFiles(directory=str(snapshot_dir)), name="snapshots")


# ═══════════════════════════════════════════════════════════════════
# Register Routers
# ═══════════════════════════════════════════════════════════════════

from app.routes.cameras import router as cameras_router
from app.routes.stream import router as stream_router
from app.routes.violations import router as violations_router
from app.routes.status import router as status_router
from app.websocket.alerts import router as websocket_router

app.include_router(cameras_router)
app.include_router(stream_router)
app.include_router(violations_router)
app.include_router(status_router)
app.include_router(websocket_router)


# ═══════════════════════════════════════════════════════════════════
# SPA Catch-All Routes (frontend compatibility)
# ═══════════════════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
@app.get("/violations", response_class=HTMLResponse)
@app.get("/cameras-page", response_class=HTMLResponse)
@app.get("/settings", response_class=HTMLResponse)
@app.get("/timeline", response_class=HTMLResponse)
async def dashboard():
    """Serve the single-page application for all frontend routes."""
    index_path = static_dir / "index.html"
    if index_path.exists():
        return HTMLResponse(index_path.read_text(encoding="utf-8"))
    return HTMLResponse(
        "<h1>SafeSight CCTV</h1><p>Static files not found. "
        "Place your frontend in the static/ directory.</p>",
        status_code=200,
    )


# ═══════════════════════════════════════════════════════════════════
# Entry Point
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn

    logger.info("Starting SafeSight CCTV Multi-Camera Server...")
    uvicorn.run(
        "app.main:app",
        host=config.SERVER_HOST,
        port=config.SERVER_PORT,
        log_level="info",
        access_log=False,
    )