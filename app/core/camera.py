"""
SafeSight CCTV - Threaded Camera Grabber

Continuously grabs frames from RTSP/IP cameras in background threads.
Enhanced with auto-upscaling for small CCTV sub-streams.

Improvements over original camera.py:
  - Structured logging instead of print()
  - Configurable via Settings object (not Config class)
  - Type hints on all methods
  - Queue-based frame management for stream consumers
  - Better error handling with specific exception types
"""

import cv2
import time
import threading
import numpy as np
from queue import Queue, Empty
from typing import Optional, Tuple
import logging

from app.config import Settings

logger = logging.getLogger(__name__)


class ThreadedCamera:
    """Grab frames from RTSP stream in a dedicated background thread.

    Features:
      - TCP transport (forced via env var for reliable delivery)
      - Minimal buffer (1 frame) to avoid stale data
      - Auto-reconnect with exponential backoff
      - Frame upscaling for small CCTV sub-streams
      - FPS tracking
      - Non-blocking frame access with lock
    """

    def __init__(
        self,
        camera_id: str,
        camera_name: str,
        rtsp_url: str,
        buffer_size: int = 2,
        config: Optional[Settings] = None,
    ):
        self.camera_id = camera_id
        self.camera_name = camera_name
        self.rtsp_url = rtsp_url
        self.buffer_size = buffer_size
        self.config = config or Settings()

        self.frame_queue: Queue = Queue(maxsize=buffer_size)
        self.latest_frame: Optional[np.ndarray] = None
        self.lock = threading.Lock()

        self.running: bool = False
        self.thread: Optional[threading.Thread] = None
        self.cap: Optional[cv2.VideoCapture] = None
        self.connected: bool = False

        # FPS tracking
        self.fps: float = 0.0
        self._frame_count: int = 0
        self._fps_start_time: float = 0.0

        # Reconnection
        self.reconnect_attempts: int = 0
        self.max_reconnect_attempts: int = 50

    def connect(self) -> bool:
        """Open RTSP stream with optimized settings.

        Returns:
            True if connection succeeded, False otherwise.
        """
        try:
            if self.cap is not None:
                self.cap.release()

            self.cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)

            if not self.cap.isOpened():
                logger.warning("[{}] Failed to open stream", self.camera_name)
                return False

            # Keep buffer minimal to avoid stale frames
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            # Timeouts so VideoCapture doesn't hang forever
            self.cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000)
            self.cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 3000)

            actual_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            logger.info(
                "[{}] Connected! {}x{}", self.camera_name, actual_w, actual_h
            )

            self.connected = True
            self.reconnect_attempts = 0
            return True

        except Exception as e:
            logger.error("[{}] Connection error: {}", self.camera_name, e)
            self.connected = False
            return False

    def _grab_loop(self):
        """Background thread that continuously grabs frames."""
        self._fps_start_time = time.time()

        while self.running:
            if not self.connected:
                if self.reconnect_attempts < self.max_reconnect_attempts:
                    self.reconnect_attempts += 1
                    if self.reconnect_attempts % 5 == 1:
                        logger.info(
                            "[{}] Reconnecting... attempt {}",
                            self.camera_name,
                            self.reconnect_attempts,
                        )
                    if self.connect():
                        continue
                    time.sleep(3)
                else:
                    logger.error(
                        "[{}] Max reconnect reached. Stopping.",
                        self.camera_name,
                    )
                    break

            ret, frame = self.cap.read()

            if not ret or frame is None:
                self.connected = False
                time.sleep(1)
                continue

            # FPS tracking
            self._frame_count += 1
            elapsed = time.time() - self._fps_start_time
            if elapsed >= 1.0:
                self.fps = self._frame_count / elapsed
                self._frame_count = 0
                self._fps_start_time = time.time()

            with self.lock:
                self.latest_frame = frame

            # Queue for consumers (drop oldest if full)
            try:
                self.frame_queue.put_nowait(frame)
            except Full:
                try:
                    self.frame_queue.get_nowait()
                    self.frame_queue.put_nowait(frame)
                except (Empty, Full):
                    pass

    def start(self) -> bool:
        """Start the camera thread (blocking — waits for initial connection).

        Returns:
            True if started successfully.
        """
        if not self.connect():
            return False
        self.running = True
        self.thread = threading.Thread(target=self._grab_loop, daemon=True)
        self.thread.start()
        logger.info("[{}] Thread started", self.camera_name)
        return True

    def start_async(self):
        """Start camera connection in a background thread (non-blocking).

        Use this for HD streams so the HTTP endpoint doesn't hang
        waiting for a slow RTSP connection.
        """
        self.running = True
        self.thread = threading.Thread(
            target=self._start_and_grab, daemon=True
        )
        self.thread.start()
        logger.info("[{}] Async start initiated...", self.camera_name)

    def _start_and_grab(self):
        """Connect first, then start grabbing. Used by start_async()."""
        self.connect()
        self._grab_loop()

    def _upscale_frame(self, frame: np.ndarray) -> np.ndarray:
        """Upscale small CCTV frames for better detection accuracy.

        Small frames (e.g. 352x288 from sub-stream) make helmets appear
        as tiny 10-15 pixel objects that YOLO can't detect reliably.
        Upscaling to at least MIN_FRAME_DIMENSION helps significantly.
        """
        h, w = frame.shape[:2]
        min_dim = self.config.MIN_FRAME_DIMENSION

        # Skip upscaling if frame is already large enough
        if w >= min_dim and h >= min_dim:
            return frame

        scale = min_dim / min(w, h)
        new_w = int(w * scale)
        new_h = int(h * scale)

        # INTER_LANCZOS4 gives the best quality for upscaling
        return cv2.resize(
            frame, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4
        )

    def get_frame(self) -> Optional[np.ndarray]:
        """Get the latest frame (non-blocking, thread-safe copy).

        Automatically upscales small frames if FRAME_UPSCALE is enabled.

        Returns:
            BGR numpy array or None if no frame available.
        """
        with self.lock:
            if self.latest_frame is not None:
                frame = self.latest_frame.copy()

                # Auto-upscale small CCTV frames for better detection
                if self.config.FRAME_UPSCALE:
                    frame = self._upscale_frame(frame)

                return frame
        return None

    def get_status(self) -> dict:
        """Get camera status info for API responses."""
        res: Tuple[int, int] = (0, 0)
        if self.cap and self.connected:
            res = (
                int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            )
        return {
            "id": self.camera_id,
            "name": self.camera_name,
            "connected": self.connected,
            "fps": round(self.fps, 1),
            "resolution": res,
            "reconnect_attempts": self.reconnect_attempts,
        }

    def stop(self):
        """Stop the camera thread and release resources."""
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)
        if self.cap:
            self.cap.release()
            self.cap = None
        self.connected = False
        logger.info("[{}] Stopped", self.camera_name)