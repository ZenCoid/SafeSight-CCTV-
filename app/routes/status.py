"""
SafeSight CCTV - Status API Routes

Endpoints for system status and statistics dashboard.

Routes:
  GET /api/status — Full system status (cameras, detector, detection toggle states)
  GET /api/stats  — Aggregate statistics (detection + violations)
"""

import logging
from datetime import datetime
from fastapi import APIRouter, Request

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/status")
async def get_status(request: Request):
    """Get full system status.

    Response format matches existing frontend:
    {
        "cameras": {id: {id, name, connected, fps, resolution, reconnect_attempts}},
        "detector": {total_detections, cameras: {id: {total, no_helmet, helmet, worker}}},
        "detection_enabled": {id: bool},
        "server_time": str
    }
    """
    state = request.app.state

    camera_status = {}
    for cid, cam in state.cameras.items():
        camera_status[cid] = cam.get_status()

    detector_stats = state.detector.get_stats() if state.detector else {}

    return {
        "cameras": camera_status,
        "detector": detector_stats,
        "detection_enabled": state.detection_enabled,
        "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


@router.get("/api/stats")
async def get_stats(request: Request):
    """Get aggregate statistics for dashboard.

    Response format matches existing frontend:
    {
        "detection": {...},
        "violations": {...},
        "cameras": int,
        "cameras_online": int
    }
    """
    state = request.app.state

    det_stats = state.detector.get_stats() if state.detector else {}
    db_stats = state.database.get_stats()

    return {
        "detection": det_stats,
        "violations": db_stats,
        "cameras": len(state.cameras),
        "cameras_online": sum(
            1 for c in state.cameras.values() if c.connected
        ),
    }