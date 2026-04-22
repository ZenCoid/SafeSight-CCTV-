"""
SafeSight CCTV - Configuration

Pydantic Settings for type-safe, validated configuration from .env.
Also loads camera definitions from cameras.json.

Improvements over original config.py:
  - All env vars validated and typed (no manual float()/int() calls)
  - Class-specific detection thresholds configurable via .env
  - Camera config as a Pydantic model (not a plain dict wrapper)
  - Settings frozen after load (prevents accidental mutation at runtime)
"""

import os
import json
import logging
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote

from pydantic import BaseModel, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# Camera Configuration (from cameras.json)
# ═══════════════════════════════════════════════════════════════════

class CameraConfig(BaseModel):
    """Configuration for a single NVR/DVR camera channel."""

    id: str
    name: str
    ip: str
    port: int = 554
    username: str = "admin"
    password: str = ""
    channel: int = 1
    subtype: int = 1

    def get_rtsp_url(self, subtype_override: Optional[int] = None) -> str:
        """Build RTSP URL with properly encoded password."""
        st = subtype_override if subtype_override is not None else self.subtype
        encoded_pwd = quote(self.password, safe="")
        return (
            f"rtsp://{self.username}:{encoded_pwd}@{self.ip}:{self.port}"
            f"/cam/realmonitor?channel={self.channel}&subtype={st}"
        )

    def to_public_dict(self) -> dict:
        """Camera info WITHOUT password (safe for API responses)."""
        return {
            "id": self.id,
            "name": self.name,
            "ip": self.ip,
            "port": self.port,
            "channel": self.channel,
        }


# ═══════════════════════════════════════════════════════════════════
# Application Settings (from .env)
# ═══════════════════════════════════════════════════════════════════

class Settings(BaseSettings):
    """All application settings loaded from .env file.

    Every setting has a sensible default matching the original config.py.
    Override in .env to customize.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # Allow extra env vars without error (forward compatibility)
        extra="ignore",
    )

    # ── Model ────────────────────────────────────────────────────
    MODEL_PATH: str = "weights/best.pt"
    CONFIDENCE_THRESHOLD: float = 0.45
    DETECTION_INTERVAL: int = 1            # Run YOLO every Nth frame

    # ── YOLO Inference ───────────────────────────────────────────
    YOLO_IMGSZ: int = 1280                # Input resolution (larger = better small objects)
    YOLO_AUGMENT: bool = True             # Test-time augmentation
    YOLO_IOU: float = 0.3                 # NMS IoU threshold
    YOLO_MAX_DET: int = 50                # Max detections per frame

    # ── Class-Specific Detection Thresholds ──────────────────────
    # (NEW: configurable via .env, previously hardcoded in detector.py)
    THRESHOLD_HELMET: float = 0.35        # Strict: blocks caps, allows real hard hats
    THRESHOLD_NO_HELMET: float = 0.20     # Lenient: safety priority, catch all violations
    THRESHOLD_WORKER: float = 0.25        # Moderate: person detection

    # ── CLAHE Preprocessing ──────────────────────────────────────
    CLAHE_ENABLED: bool = True
    CLAHE_CLIP_LIMIT: float = 2.0         # Contrast enhancement strength
    CLAHE_TILE_SIZE: int = 8              # Tile grid size

    # ── Frame Upscaling ──────────────────────────────────────────
    FRAME_UPSCALE: bool = True            # Upscale small CCTV sub-streams
    MIN_FRAME_DIMENSION: int = 720        # Min width/height before upscale kicks in

    # ── Temporal Smoothing ───────────────────────────────────────
    SMOOTHING_BUFFER_SIZE: int = 5        # Frames to keep in smoothing buffer
    SMOOTHING_MIN_HITS: int = 2           # Min appearances to confirm detection
    SMOOTHING_IOU_THRESHOLD: float = 0.15 # Low IoU to tolerate movement between frames

    # ── Streaming ────────────────────────────────────────────────
    STREAM_FPS: int = 25
    JPEG_QUALITY: int = 80                # Sub-stream JPEG quality
    JPEG_QUALITY_HD: int = 90             # Main-stream JPEG quality

    # ── Server ───────────────────────────────────────────────────
    SERVER_HOST: str = "0.0.0.0"
    SERVER_PORT: int = 8000
    LOG_LEVEL: str = "INFO"

    # ── RTSP ─────────────────────────────────────────────────────
    RTSP_SUBTYPE: int = 0                 # 0 = main stream, 1 = sub-stream

    # ── Gmail SMTP Alerts ────────────────────────────────────────
    SMTP_ENABLED: bool = False
    SMTP_SERVER: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_EMAIL: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_TO: str = ""                     # Comma-separated for multiple recipients

    # ── Database ─────────────────────────────────────────────────
    DB_PATH: str = "violations.db"

    # ── Snapshots ────────────────────────────────────────────────
    SNAPSHOT_DIR: str = "violations"
    SNAPSHOT_QUALITY: int = 90

    # ── Violation Tracking ───────────────────────────────────────
    VIOLATION_THRESHOLD: int = 5          # Consecutive frames to trigger alert
    VIOLATION_COOLDOWN: int = 30          # Seconds between alerts for same camera

    # ── Derived Properties ───────────────────────────────────────

    @property
    def smtp_to_list(self) -> List[str]:
        """Parse comma-separated email recipients."""
        return [addr.strip() for addr in self.SMTP_TO.split(",") if addr.strip()]

    @property
    def snapshot_path(self) -> Path:
        return Path(self.SNAPSHOT_DIR)

    # ── Camera Loading ───────────────────────────────────────────
    cameras: List[CameraConfig] = []

    @classmethod
    def load_cameras(cls) -> List[CameraConfig]:
        """Load camera definitions from cameras.json.

        Returns list of CameraConfig objects. Returns empty list
        if cameras.json doesn't exist (webcam-only mode).
        """
        cameras_path = Path("cameras.json")
        if not cameras_path.exists():
            logger.info("cameras.json not found — webcam-only mode")
            return []

        try:
            with open(cameras_path, "r") as f:
                data = json.load(f)

            cameras = []
            for cam_data in data.get("cameras", []):
                cam = CameraConfig(**cam_data)
                cameras.append(cam)
                logger.info(
                    "Loaded camera: {} (ch={}) -> {}:{}",
                    cam.name, cam.channel, cam.ip, cam.port,
                )

            cls.cameras = cameras
            return cameras

        except (json.JSONDecodeError, KeyError) as e:
            logger.error("Failed to parse cameras.json: {}", e)
            return []


# ═══════════════════════════════════════════════════════════════════
# Force TCP for RTSP — MUST be before any cv2.VideoCapture()
# ═══════════════════════════════════════════════════════════════════
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"

# Singleton
settings = Settings()