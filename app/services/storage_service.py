"""
SafeSight CCTV - Snapshot Storage Service

Handles saving annotated violation snapshots to disk.
Snapshots include detection boxes, labels, and a timestamp overlay.

Improvements over original (embedded in detector.py):
  - Standalone service (injectable, testable)
  - Timestamp overlay on every snapshot
  - Configurable quality from Settings
  - Auto-creates snapshot directory
"""

import os
import cv2
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from app.config import Settings

logger = logging.getLogger(__name__)


class StorageService:
    """Manages violation snapshot storage."""

    def __init__(self, config: Optional[Settings] = None):
        self.config = config or Settings()
        self.snapshot_dir = Path(self.config.SNAPSHOT_DIR)
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Snapshot directory: {}", self.snapshot_dir.resolve())

    def save_snapshot(
        self,
        camera_id: str,
        frame,
        detections: list,
    ) -> Optional[str]:
        """Save an annotated violation snapshot.

        Draws detection boxes and timestamp overlay on the frame
        before saving as JPEG.

        Args:
            camera_id: Camera that captured the frame.
            frame: BGR numpy array.
            detections: List of detection dicts.

        Returns:
            File path of saved snapshot, or None on failure.
        """
        try:
            annotated = frame.copy()

            # Draw detection boxes (same style as detector)
            for det in detections:
                x1, y1, x2, y2 = det["bbox"]
                cls_id = det["class_id"]
                cls_name = det["class_name"]
                conf = det["confidence"]

                colors = {0: (0, 200, 0), 1: (0, 0, 255), 2: (255, 165, 0)}
                color = colors.get(cls_id, (255, 255, 255))

                h, w = annotated.shape[:2]
                x1 = max(0, min(x1, w - 1))
                y1 = max(0, min(y1, h - 1))
                x2 = max(0, min(x2, w - 1))
                y2 = max(0, min(y2, h - 1))

                cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 3)

                label = f"{cls_name} {conf:.0%}"
                font = cv2.FONT_HERSHEY_SIMPLEX
                font_scale = 0.55
                thickness = 2
                (text_w, text_h), _ = cv2.getTextSize(
                    label, font, font_scale, thickness
                )
                label_y = max(y1 - 6, text_h + 4)
                cv2.rectangle(
                    annotated,
                    (x1, label_y - text_h - 4),
                    (x1 + text_w + 6, label_y + 2),
                    color, -1,
                )
                cv2.putText(
                    annotated, label, (x1 + 3, label_y - 2),
                    font, font_scale, (255, 255, 255), thickness, cv2.LINE_AA,
                )

            # Timestamp overlay at bottom
            ts_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cv2.putText(
                annotated,
                f"SafeSight AI | {camera_id} | {ts_text}",
                (10, annotated.shape[0] - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA,
            )

            # Save
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            filename = f"{camera_id}_{timestamp}.jpg"
            filepath = self.snapshot_dir / filename

            cv2.imwrite(
                str(filepath), annotated,
                [cv2.IMWRITE_JPEG_QUALITY, self.config.SNAPSHOT_QUALITY],
            )
            logger.info("Snapshot saved: {}", filepath)
            return str(filepath)

        except Exception as e:
            logger.error("Failed to save snapshot: {}", e)
            return None

    def list_snapshots(self, limit: int = 50) -> List[dict]:
        """List recent snapshots."""
        snapshots = []
        for filepath in sorted(
            self.snapshot_dir.glob("*.jpg"), key=lambda p: p.stat().st_mtime, reverse=True
        )[:limit]:
            snapshots.append({
                "filename": filepath.name,
                "path": str(filepath.resolve()),
                "size_bytes": filepath.stat().st_size,
            })
        return snapshots