"""
SafeSight CCTV - MJPEG Stream Server
Serves the annotated video feed as an MJPEG stream to the browser.
The video stream runs independently from detection for maximum smoothness.
"""
import cv2
import time
import threading
import numpy as np
from camera import ThreadedCamera
from detector import YOLODetector
from config import Config


class MJPEGStreamer:
    """Produces MJPEG stream from camera + detection pipeline."""

    def __init__(self, camera: ThreadedCamera, detector: YOLODetector):
        self.camera = camera
        self.detector = detector
        self.running = False
        self.clients = 0
        self.fps = 0
        self._frame_count = 0
        self._start_time = time.time()
        self._stop_event = threading.Event()

    def generate_frames(self):
        """
        Generator that yields JPEG frames as bytes.
        Used by FastAPI StreamingResponse for MJPEG.
        """
        print("[Streamer] Client connected, starting stream...")
        self.clients += 1
        interval = 1.0 / Config.STREAM_FPS

        try:
            while self.running:
                frame_start = time.time()

                # Get latest frame from camera (non-blocking)
                frame = self.camera.get_frame()
                if frame is None:
                    # Send a "no signal" frame
                    no_signal = np.zeros((720, 1280, 3), dtype=np.uint8)
                    cv2.putText(
                        no_signal,
                        "Connecting to camera...",
                        (400, 360),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        1.0,
                        (255, 255, 255),
                        2,
                    )
                    _, jpeg = cv2.imencode(".jpg", no_signal, [cv2.IMWRITE_JPEG_QUALITY, 70])
                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n"
                    )
                    time.sleep(0.5)
                    continue

                # Run detection + get annotated frame
                annotated, detections = self.detector.detect(frame)

                # Encode to JPEG
                _, jpeg = cv2.imencode(".jpg", annotated, [
                    cv2.IMWRITE_JPEG_QUALITY, Config.JPEG_QUALITY
                ])

                # Track FPS
                self._frame_count += 1
                elapsed = time.time() - self._start_time
                if elapsed >= 1.0:
                    self.fps = round(self._frame_count / elapsed, 1)
                    self._frame_count = 0
                    self._start_time = time.time()

                # Yield MJPEG frame
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n"
                )

                # Control frame rate
                process_time = time.time() - frame_start
                sleep_time = interval - process_time
                if sleep_time > 0:
                    time.sleep(sleep_time)

        except GeneratorExit:
            pass
        finally:
            self.clients -= 1
            print(f"[Streamer] Client disconnected. Active clients: {self.clients}")

    def start(self):
        """Start the streamer."""
        self.running = True
        print("[Streamer] Started")

    def stop(self):
        """Stop the streamer."""
        self.running = False
        print("[Streamer] Stopped")

    def get_status(self) -> dict:
        """Get streamer status."""
        return {
            "running": self.running,
            "active_clients": self.clients,
            "fps": self.fps,
            "target_fps": Config.STREAM_FPS,
            "jpeg_quality": Config.JPEG_QUALITY,
        }