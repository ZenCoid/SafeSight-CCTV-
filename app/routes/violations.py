"""
SafeSight CCTV - Violation API Routes

Endpoints for violation history, stats, and test alerts.
Response formats match existing frontend expectations.

Routes:
  GET  /api/violations           — Violation history with filtering
  POST /api/violations/send_test — Send a test email alert
"""

import os
import logging
from fastapi import APIRouter, Request, Query

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/violations")
async def get_violations(
    request: Request,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    hours: int = Query(24, ge=1, le=8760),
    camera_id: str = Query(None),
):
    """Get violation history with optional filtering.

    Response format matches existing frontend:
    {"violations": [...], "count": int}

    Each violation includes a snapshot_url if a snapshot exists.
    """
    state = request.app.state
    violations = state.database.get_violations(
        limit=limit, offset=offset, hours=hours, camera_id=camera_id
    )

    # Add snapshot URL for frontend image display
    for v in violations:
        if v.get("snapshot_path"):
            v["snapshot_url"] = f"/snapshots/{os.path.basename(v['snapshot_path'])}"

    return {"violations": violations, "count": len(violations)}


@router.post("/api/violations/send_test")
async def send_test_alert(request: Request):
    """Send a test violation email (no snapshot).

    Returns: {"success": bool}
    """
    state = request.app.state
    success = state.alert_service.send_violation_alert(
        camera_name="Test Camera",
        detection_type="no_helmet",
        confidence=0.85,
        snapshot_path=None,
    )
    logger.info("Test alert sent: {}", success)
    return {"success": success}