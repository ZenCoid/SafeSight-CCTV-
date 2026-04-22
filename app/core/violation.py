"""
SafeSight CCTV - Violation Tracker

Separated from detector.py for cleaner architecture.
Tracks consecutive violation frames with buffer and cooldown per camera.

A violation alert fires when:
  1. N consecutive detection frames show "NoHelmet" (buffer)
  2. At least M seconds have passed since the last alert (cooldown)

Improvements over original (embedded in detector.py):
  - Standalone class (detector doesn't need to know about alerts/DB)
  - Time-windowed buffer (not just counter) to handle variable frame rates
  - Clean separation of concerns
"""

import time
import logging
from typing import Dict, List

from app.config import Settings

logger = logging.getLogger(__name__)


class ViolationTracker:
    """Per-camera violation detection with buffer and cooldown.

    Uses a time-windowed approach: violations are counted within a
    sliding time window, not just a simple counter. This handles
    variable frame rates and detection intervals correctly.
    """

    def __init__(self, config: Settings):
        self.config = config
        self.threshold = config.VIOLATION_THRESHOLD        # e.g., 5 frames
        self.cooldown = config.VIOLATION_COOLDOWN          # e.g., 30 seconds

        # Per-camera state
        self._buffers: Dict[str, List[float]] = {}         # camera_id -> [timestamps]
        self._last_alert: Dict[str, float] = {}            # camera_id -> timestamp
        self._violation_counts: Dict[str, int] = {}        # camera_id -> total alerts sent

        logger.info(
            "ViolationTracker ready (threshold={} frames, cooldown={}s)",
            self.threshold, self.cooldown,
        )

    def check(self, camera_id: str, has_violation: bool) -> tuple:
        """Check if a violation should trigger an alert.

        Args:
            camera_id: Camera identifier.
            has_violation: Whether current frame has a NoHelmet detection.

        Returns:
            Tuple of (should_alert: bool, buffer_count: int, frames_needed: int)
        """
        now = time.time()

        # Reset buffer if no violation in this frame
        if not has_violation:
            self._buffers[camera_id] = []
            return (False, 0, self.threshold)

        # Add current timestamp to buffer
        buf = self._buffers.setdefault(camera_id, [])
        buf.append(now)

        # Keep only recent entries (last 2x cooldown as safety window)
        window = self.cooldown * 2
        self._buffers[camera_id] = [t for t in buf if now - t <= window]

        current_count = len(self._buffers[camera_id])

        # Check if buffer threshold is met
        if current_count >= self.threshold:
            # Check cooldown
            last = self._last_alert.get(camera_id, 0)
            time_since = now - last

            if time_since >= self.cooldown:
                # Fire alert
                self._last_alert[camera_id] = now
                self._buffers[camera_id] = []
                self._violation_counts[camera_id] = (
                    self._violation_counts.get(camera_id, 0) + 1
                )
                logger.info(
                    "[VIOLATION] {} - No helmet after {} frames "
                    "(cooldown was {:.0f}s, total alerts: {})",
                    camera_id,
                    current_count,
                    time_since,
                    self._violation_counts[camera_id],
                )
                return (True, current_count, 0)

        return (False, current_count, max(0, self.threshold - current_count))

    def reset(self, camera_id: str):
        """Manually reset the violation buffer for a camera."""
        self._buffers[camera_id] = []

    def get_status(self, camera_id: str) -> dict:
        """Get current tracker status for a camera."""
        now = time.time()
        buf = self._buffers.get(camera_id, [])
        last = self._last_alert.get(camera_id, 0)
        return {
            "camera_id": camera_id,
            "buffer_count": len(buf),
            "threshold": self.threshold,
            "last_alert": last,
            "cooldown_remaining": max(0, self.cooldown - (now - last)) if last else 0,
            "total_alerts": self._violation_counts.get(camera_id, 0),
        }