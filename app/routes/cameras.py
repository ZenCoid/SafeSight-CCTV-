"""
SafeSight CCTV - Camera API Routes

Endpoints for camera management, detection toggle, and reconnection.
All response formats match the existing frontend expectations exactly.

Routes:
  GET  /api/cameras              — List all cameras with status
  POST /api/detection/toggle/ID  — Enable/disable detection on a camera
  POST /api/camera/reconnect/ID  — Reconnect a single camera
  POST /api/camera/reconnect_all — Reconnect all cameras
"""

import logging
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.config import Settings

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/cameras")
async def camera_list(request: Request):
    """List all cameras with connection status and detection state.

    Response format matches existing frontend expectations:
    {"cameras": [{id, name, ip, channel, connected, fps, resolution, detection_enabled}]}
    """
    state = request.app.state

    result = []
    for cam_conf in state.config.cameras:
        cam = state.cameras.get(cam_conf.id)
        info = {
            "id": cam_conf.id,
            "name": cam_conf.name,
            "ip": cam_conf.ip,
            "channel": cam_conf.channel,
            "connected": cam.connected if cam else False,
            "fps": cam.get_status()["fps"] if cam else 0,
            "resolution": cam.get_status()["resolution"] if cam else (0, 0),
            "detection_enabled": state.detection_enabled.get(cam_conf.id, True),
        }
        result.append(info)

    return {"cameras": result}


@router.post("/api/detection/toggle/{camera_id}")
async def toggle_detection(request: Request, camera_id: str):
    """Toggle detection on/off for a specific camera.

    Returns: {"camera_id": str, "enabled": bool}
    """
    state = request.app.state

    if camera_id not in state.cameras:
        return JSONResponse(
            status_code=404,
            content={"error": "Camera not found"},
        )

    state.detection_enabled[camera_id] = not state.detection_enabled.get(camera_id, True)
    logger.info(
        "Detection {} for camera {}", 
        "enabled" if state.detection_enabled[camera_id] else "disabled",
        camera_id,
    )
    return {"camera_id": camera_id, "enabled": state.detection_enabled[camera_id]}


@router.post("/api/camera/reconnect/{camera_id}")
async def reconnect_camera(request: Request, camera_id: str):
    """Force reconnect a single camera.

    Returns: {"camera_id": str, "success": bool}
    """
    state = request.app.state
    cam = state.cameras.get(camera_id)

    if not cam:
        return JSONResponse(
            status_code=404,
            content={"error": "Camera not found"},
        )

    success = cam.connect()
    logger.info("Reconnect {} for camera {}: {}", camera_id, "OK" if success else "FAILED", camera_id)
    return {"camera_id": camera_id, "success": success}


@router.post("/api/camera/reconnect_all")
async def reconnect_all(request: Request):
    """Force reconnect all cameras.

    Returns: {camera_id: bool, ...}
    """
    state = request.app.state
    results = {}
    for cid, cam in state.cameras.items():
        results[cid] = cam.connect()
    logger.info("Reconnect all: {}", results)
    return results