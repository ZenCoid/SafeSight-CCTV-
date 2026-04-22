"""
SafeSight CCTV - Stream API Routes

MJPEG video streaming endpoints with real-time detection overlays.

Routes:
  GET /stream/webcam      — Webcam stream (mirror flipped)
  GET /stream/{camera_id} — Camera stream with detection
"""

import cv2
import time
import numpy as np
import logging
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse, JSONResponse

from app.config import Settings

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/stream/webcam")
async def webcam_stream(request: Request):
    """MJPEG video stream from the laptop's built-in webcam.

    Uses the same YOLO detection pipeline as CCTV cameras.
    Mirror-flipped for natural webcam experience.
    """
    state = request.app.state
    config = state.config
    det = state.detector
    interval = 1.0 / config.STREAM_FPS

    def generate():
        cap = cv2.VideoCapture(0)

        if not cap.isOpened():
            logger.error("Failed to open webcam")
            no_sig = _create_no_signal_frame("Webcam")
            _, jpeg = cv2.imencode(".jpg", no_sig, [cv2.IMWRITE_JPEG_QUALITY, 70])
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n"
            return

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        logger.info("Webcam connected! {}x{}", actual_w, actual_h)

        try:
            while True:
                frame_start = time.time()

                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.1)
                    continue

                # Mirror flip for natural webcam experience
                frame = cv2.flip(frame, 1)

                # Run detection
                if det and det.model:
                    annotated, _ = det.detect("webcam", frame)
                else:
                    annotated = frame

                _, jpeg = cv2.imencode(".jpg", annotated, [
                    cv2.IMWRITE_JPEG_QUALITY, config.JPEG_QUALITY
                ])
                yield (
                    b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                    + jpeg.tobytes() + b"\r\n"
                )

                elapsed = time.time() - frame_start
                sleep_time = interval - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)
        finally:
            cap.release()
            logger.info("Webcam released")

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.get("/stream/{camera_id}")
async def video_stream(request: Request, camera_id: str):
    """MJPEG video stream from a CCTV camera with detection overlays.

    Returns the annotated feed with bounding boxes drawn in real-time.
    Supports toggling detection on/off per camera.
    """
    state = request.app.state
    config = state.config
    cam = state.cameras.get(camera_id)

    if not cam:
        return JSONResponse(
            status_code=404,
            content={"error": f"Camera '{camera_id}' not found"},
        )

    det = state.detector
    interval = 1.0 / config.STREAM_FPS

    def generate():
        while True:
            frame_start = time.time()

            frame = cam.get_frame()
            if frame is None:
                no_sig = _create_no_signal_frame(camera_id)
                _, jpeg = cv2.imencode(".jpg", no_sig, [cv2.IMWRITE_JPEG_QUALITY, 70])
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n"
                time.sleep(0.5)
                continue

            if state.detection_enabled.get(camera_id, True) and det and det.model:
                annotated, _ = det.detect(camera_id, frame)
            else:
                annotated = frame

            _, jpeg = cv2.imencode(".jpg", annotated, [
                cv2.IMWRITE_JPEG_QUALITY, config.JPEG_QUALITY
            ])
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n"

            elapsed = time.time() - frame_start
            sleep_time = interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


def _create_no_signal_frame(camera_name: str) -> np.ndarray:
    """Create a 'Connecting...' placeholder frame."""
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    cv2.putText(frame, "Connecting...", (500, 340),
                cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 2)
    cv2.putText(frame, camera_name, (500, 380),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (150, 150, 150), 1)
    return frame