"""
SafeSight CCTV - Multi-Camera Configuration
Loads camera settings from cameras.json and .env file.
Supports NVR/DVR setups where all cameras share one IP with different channels.
"""
import os
import json
from urllib.parse import quote
from pathlib import Path
from dotenv import load_dotenv

# Load .env
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)


class CameraConfig:
    """Configuration for a single camera."""

    def __init__(self, data: dict):
        self.id = data["id"]
        self.name = data["name"]
        self.ip = data["ip"]
        self.port = data.get("port", 554)
        self.username = data.get("username", "admin")
        self.password = data.get("password", "")
        self.channel = data.get("channel", 1)
        self.subtype = data.get("subtype", 1)

    def get_rtsp_url(self) -> str:
        encoded_pwd = quote(self.password, safe='')
        return (
            f"rtsp://{self.username}:{encoded_pwd}@{self.ip}:{self.port}"
            f"/cam/realmonitor?channel={self.channel}&subtype={self.subtype}"
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "ip": self.ip,
            "port": self.port,
            "channel": self.channel,
            "connected": False,
        }


class Config:
    # Model
    MODEL_PATH = os.getenv("MODEL_PATH", "models/best.pt")
    CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.45"))
    DETECTION_INTERVAL = int(os.getenv("DETECTION_INTERVAL", "1"))

    # Streaming — single camera view means we can afford high quality
    STREAM_FPS = int(os.getenv("STREAM_FPS", "25"))
    JPEG_QUALITY = int(os.getenv("JPEG_QUALITY", "80"))
    JPEG_QUALITY_HD = int(os.getenv("JPEG_QUALITY_HD", "90"))

    # Server
    SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
    SERVER_PORT = int(os.getenv("SERVER_PORT", "8000"))

    # Database
    DB_PATH = "violations.db"

    # Violation snapshots
    SNAPSHOT_DIR = "violations"
    SNAPSHOT_QUALITY = 90

    # Violation Buffer — prevents false positives and spam
    VIOLATION_THRESHOLD = int(os.getenv("VIOLATION_THRESHOLD", "5"))
    VIOLATION_COOLDOWN = int(os.getenv("VIOLATION_COOLDOWN", "30"))

    # Cameras (loaded from cameras.json)
    cameras: list[CameraConfig] = []

    @staticmethod
    def load_cameras() -> list[CameraConfig]:
        """Load camera definitions from cameras.json."""
        cameras_path = Path(__file__).parent / "cameras.json"
        if not cameras_path.exists():
            print(f"[Config] cameras.json not found at {cameras_path}")
            return []

        with open(cameras_path, "r") as f:
            data = json.load(f)

        cameras = []
        for cam_data in data.get("cameras", []):
            cam = CameraConfig(cam_data)
            cameras.append(cam)
            print(f"[Config] Loaded camera: {cam.name} (ch={cam.channel}) -> {cam.ip}:{cam.port}")

        Config.cameras = cameras
        return cameras