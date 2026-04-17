"""
SafeSight CCTV - Threaded RTSP Camera Grabber
Continuously grabs frames from an IP camera in a background thread.
"""
import os
import cv2
import time
import threading
import numpy as np
from queue import Queue

# MUST be set BEFORE any cv2.VideoCapture() call
# Forces TCP instead of UDP — TCP guarantees frame delivery, UDP drops packets
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"


class ThreadedCamera:
    """Grab frames from RTSP stream in a dedicated thread."""

    def __init__(self, camera_id: str, camera_name: str, rtsp_url: str, buffer_size: int = 2):
        self.camera_id = camera_id
        self.camera_name = camera_name
        self.rtsp_url = rtsp_url
        self.buffer_size = buffer_size
        self.frame_queue: Queue = Queue(maxsize=buffer_size)
        self.latest_frame = None
        self.lock = threading.Lock()
        self.running = False
        self.thread = None
        self.cap = None
        self.connected = False
        self.fps = 0
        self.frame_count = 0
        self.start_time = None
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 50

    def connect(self) -> bool:
        """Open RTSP stream with optimized settings."""
        try:
            if self.cap is not None:
                self.cap.release()

            self.cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)

            if not self.cap.isOpened():
                print(f"[{self.camera_name}] Failed to open stream")
                return False

            # Keep buffer minimal to avoid stale frames
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            # Timeouts so VideoCapture doesn't hang forever
            self.cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000)
            self.cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 3000)

            actual_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            print(f"[{self.camera_name}] Connected! {actual_w}x{actual_h}")

            self.connected = True
            self.reconnect_attempts = 0
            return True

        except Exception as e:
            print(f"[{self.camera_name}] Connection error: {e}")
            self.connected = False
            return False

    def _grab_loop(self):
        """Background thread that continuously grabs frames."""
        self.start_time = time.time()

        while self.running:
            if not self.connected:
                if self.reconnect_attempts < self.max_reconnect_attempts:
                    self.reconnect_attempts += 1
                    if self.reconnect_attempts % 5 == 1:
                        print(f"[{self.camera_name}] Reconnecting... attempt {self.reconnect_attempts}")
                    if self.connect():
                        continue
                    time.sleep(3)
                else:
                    print(f"[{self.camera_name}] Max reconnect reached. Stopping.")
                    break

            ret, frame = self.cap.read()

            if not ret:
                self.connected = False
                time.sleep(1)
                continue

            self.frame_count += 1
            elapsed = time.time() - self.start_time
            if elapsed >= 1.0:
                self.fps = self.frame_count / elapsed
                self.frame_count = 0
                self.start_time = time.time()

            with self.lock:
                self.latest_frame = frame

            try:
                self.frame_queue.put_nowait(frame)
            except:
                try:
                    self.frame_queue.get_nowait()
                    self.frame_queue.put_nowait(frame)
                except:
                    pass

    def start(self) -> bool:
        """Start the camera thread (blocking — waits for connection)."""
        if not self.connect():
            return False
        self.running = True
        self.thread = threading.Thread(target=self._grab_loop, daemon=True)
        self.thread.start()
        print(f"[{self.camera_name}] Thread started")
        return True

    def start_async(self):
        """Start camera connection in a background thread (non-blocking).
        Use this for HD streams so the HTTP endpoint doesn't hang."""
        self.running = True
        self.thread = threading.Thread(target=self._start_and_grab, daemon=True)
        self.thread.start()
        print(f"[{self.camera_name}] Async start initiated...")

    def _start_and_grab(self):
        """Connect first, then start grabbing. Used by start_async()."""
        if self.connect():
            self._grab_loop()
        else:
            self._grab_loop()

    def get_frame(self) -> np.ndarray | None:
        """Get the latest frame. Non-blocking."""
        with self.lock:
            if self.latest_frame is not None:
                return self.latest_frame.copy()
        return None

    def get_status(self) -> dict:
        """Get camera status info."""
        res = (0, 0)
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