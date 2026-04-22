"""
SafeSight CCTV - YOLO Helmet/PPE Detector

Runs YOLO inference on camera frames, draws detection boxes,
and coordinates violation tracking via the separated ViolationTracker.

Enhanced for CCTV footage:
  - CLAHE contrast preprocessing in LAB color space (shadows/overexposure fix)
  - YOLO high input resolution (better small object detection)
  - Class-specific confidence thresholds (strict helmet, lenient no-helmet)
  - Temporal detection smoothing with movement-tolerant IoU
  - Frame skipping (detection every Nth frame) for performance

Improvements over original detector.py:
  - Violation logic separated into ViolationTracker class
  - Thresholds configurable via .env (not hardcoded)
  - Snapshot saving delegated to StorageService
  - Email alerts delegated to AlertService
  - Structured logging instead of print()
  - Cleaner detection pipeline (preprocess → infer → smooth → draw)
"""

import cv2
import numpy as np
import time
import logging
from pathlib import Path
from collections import deque
from typing import List, Dict, Optional, Tuple, Any

try:
    from ultralytics import YOLO
except ImportError:
    YOLO = None

from app.config import Settings
from app.core.violation import ViolationTracker

logger = logging.getLogger(__name__)


class YOLODetector:
    """YOLO-based helmet/PPE detection with temporal smoothing.

    Pipeline:
        1. CLAHE preprocessing (LAB color space — better than grayscale)
        2. YOLO inference (high resolution, test-time augment)
        3. Class-specific threshold filtering
        4. Temporal smoothing (detection must persist across frames)
        5. Draw styled bounding boxes on frame
        6. Check violations via ViolationTracker
        7. Trigger snapshot + DB log + email if violation fires
    """

    # Class definitions (from model training)
    CLASS_NAMES: Dict[int, str] = {0: "Helmet", 1: "No Helmet", 2: "Worker"}
    CLASS_COLORS: Dict[int, Tuple[int, int, int]] = {
        0: (0, 200, 0),    # Green — Helmet
        1: (0, 0, 255),    # Red — No Helmet
        2: (255, 165, 0),  # Orange — Worker
    }

    def __init__(
        self,
        config: Optional[Settings] = None,
        violation_tracker: Optional[ViolationTracker] = None,
    ):
        self.config = config or Settings()
        self.model: Optional[Any] = None
        self.model_path: str = self.config.MODEL_PATH

        # Class-specific thresholds (from .env or defaults)
        self.class_confidence: Dict[int, float] = {
            0: self.config.THRESHOLD_HELMET,        # 0.35
            1: self.config.THRESHOLD_NO_HELMET,      # 0.20
            2: self.config.THRESHOLD_WORKER,         # 0.25
        }

        # Frame counting per camera (for detection interval)
        self.frame_counts: Dict[str, int] = {}

        # Last confirmed detections per camera (for drawing between inference frames)
        self.last_detections: Dict[str, List[dict]] = {}

        # Temporal smoothing buffers per camera
        self.detection_buffers: Dict[str, deque] = {}
        self.smoothing_buffer_size = self.config.SMOOTHING_BUFFER_SIZE
        self.smoothing_min_hits = self.config.SMOOTHING_MIN_HITS
        self.smoothing_iou = self.config.SMOOTHING_IOU_THRESHOLD

        # Violation tracker (separated class)
        self.violation_tracker = violation_tracker or ViolationTracker(self.config)

        # Callbacks for violation handling (set by main.py during setup)
        self._on_violation = None  # callback(camera_id, frame, detections, max_conf)

        # CLAHE preprocessor
        self.clahe = None
        if self.config.CLAHE_ENABLED:
            self.clahe = cv2.createCLAHE(
                clipLimit=self.config.CLAHE_CLIP_LIMIT,
                tileGridSize=(self.config.CLAHE_TILE_SIZE, self.config.CLAHE_TILE_SIZE),
            )

    def set_violation_callback(self, callback):
        """Set callback function for violation events.

        Callback signature: callback(camera_id, frame, detections, max_confidence)
        """
        self._on_violation = callback

    def load_model(self) -> bool:
        """Load YOLO model weights.

        Returns:
            True if model loaded successfully.
        """
        model_file = Path(self.model_path)
        if not model_file.exists():
            logger.error("Model file not found: {}", self.model_path)
            logger.warning("Running without detection (camera feed only)")
            return False

        if YOLO is None:
            logger.error("ultralytics not installed. Run: pip install ultralytics")
            return False

        try:
            self.model = YOLO(str(model_file))
            logger.info("Model loaded: {}", self.model_path)
            logger.info("  Input size: {}", self.config.YOLO_IMGSZ)
            logger.info("  Test-time augment: {}", self.config.YOLO_AUGMENT)
            logger.info("  CLAHE: enabled={}, clipLimit={}", self.config.CLAHE_ENABLED, self.config.CLAHE_CLIP_LIMIT)
            logger.info("  Frame upscale: {} (min {}px)", self.config.FRAME_UPSCALE, self.config.MIN_FRAME_DIMENSION)
            logger.info("  Smoothing: {} frames / {} min hits (IoU {})", self.smoothing_buffer_size, self.smoothing_min_hits, self.smoothing_iou)
            logger.info("  Class thresholds: Helmet={}, No Helmet={}, Worker={}", self.class_confidence[0], self.class_confidence[1], self.class_confidence[2])
            logger.info("  Detection interval: every {} frames", self.config.DETECTION_INTERVAL)
            logger.info("  Violation: {} frames buffer, {}s cooldown", self.config.VIOLATION_THRESHOLD, self.config.VIOLATION_COOLDOWN)
            return True
        except Exception as e:
            logger.error("Failed to load model: {}", e)
            return False

    def _preprocess_frame(self, frame: np.ndarray) -> np.ndarray:
        """Apply CLAHE contrast enhancement in LAB color space.

        This is superior to grayscale CLAHE because it enhances
        luminance while preserving color information, which helps
        the YOLO model detect colored helmets and vests better.

        Returns:
            Enhanced BGR frame.
        """
        if self.clahe is None:
            return frame
        try:
            lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            l = self.clahe.apply(l)
            enhanced = cv2.merge([l, a, b])
            enhanced = cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)
            return enhanced
        except Exception:
            return frame

    def detect(self, camera_id: str, frame: np.ndarray) -> Tuple[np.ndarray, List[dict]]:
        """Run detection on a frame. Returns (annotated_frame, detections).

        This is the main entry point called by stream generators.
        Handles frame skipping, inference, smoothing, and drawing.

        Args:
            camera_id: Camera identifier string.
            frame: BGR numpy array from camera.

        Returns:
            Tuple of (annotated BGR frame, list of detection dicts).
        """
        self.frame_counts[camera_id] = self.frame_counts.get(camera_id, 0) + 1
        frame_num = self.frame_counts[camera_id]

        # Initialize smoothing buffer for this camera
        if camera_id not in self.detection_buffers:
            self.detection_buffers[camera_id] = deque(maxlen=self.smoothing_buffer_size)

        # Run YOLO inference every Nth frame
        if self.model is not None and frame_num % self.config.DETECTION_INTERVAL == 0:
            raw_detections = self._run_inference(frame, camera_id)

            # Add to smoothing buffer
            self.detection_buffers[camera_id].append(raw_detections)

            # Get smoothed (stable) detections
            smoothed = self._smooth_detections(camera_id)
            self.last_detections[camera_id] = smoothed

            if smoothed:
                annotated = self._draw_detections(frame, smoothed)
                return annotated, smoothed
            return frame, []
        else:
            # Use previous smoothed detections to keep boxes visible
            prev = self.last_detections.get(camera_id, [])
            if prev:
                annotated = self._draw_detections(frame, prev)
                return annotated, prev
            return frame, []

    def _run_inference(self, frame: np.ndarray, camera_id: str) -> List[dict]:
        """Run YOLO inference with enhanced CCTV settings.

        Pipeline:
            1. CLAHE preprocessing (LAB color space)
            2. YOLO at very low confidence (0.10) to catch everything
            3. Apply class-specific thresholds post-inference
            4. Check violation conditions via ViolationTracker
            5. Fire violation callback if triggered

        Returns:
            List of raw detection dicts.
        """
        try:
            # Step 1: CLAHE preprocessing
            enhanced = self._preprocess_frame(frame)

            # Step 2: YOLO inference
            results = self.model(
                enhanced,
                conf=0.10,
                imgsz=self.config.YOLO_IMGSZ,
                augment=self.config.YOLO_AUGMENT,
                iou=self.config.YOLO_IOU,
                max_det=self.config.YOLO_MAX_DET,
                verbose=False,
            )

            detections = []
            has_no_helmet = False

            for result in results:
                boxes = result.boxes
                if boxes is None:
                    continue
                for box in boxes:
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int)
                    conf = float(box.conf[0])
                    cls_id = int(box.cls[0])

                    # Step 3: Class-specific threshold
                    cls_threshold = self.class_confidence.get(cls_id, 0.20)
                    if conf < cls_threshold:
                        continue

                    cls_name = self.CLASS_NAMES.get(cls_id, f"Class_{cls_id}")
                    detections.append({
                        "class_id": cls_id,
                        "class_name": cls_name,
                        "confidence": round(conf, 2),
                        "bbox": [int(x1), int(y1), int(x2), int(y2)],
                    })

                    if cls_id == 1:
                        has_no_helmet = True

            # Step 4: Check violations
            if has_no_helmet:
                should_alert, count, _ = self.violation_tracker.check(camera_id, True)
                if should_alert:
                    max_conf = max(
                        d["confidence"]
                        for d in detections
                        if d["class_id"] == 1
                    )
                    # Step 5: Fire violation callback (snapshot + DB + email)
                    if self._on_violation:
                        self._on_violation(camera_id, frame, detections, max_conf)
            else:
                self.violation_tracker.check(camera_id, False)

            return detections

        except Exception as e:
            logger.error("Inference failed for {}: {}", camera_id, e)
            return []

    def _smooth_detections(self, camera_id: str) -> List[dict]:
        """Return detections that are stable across multiple recent frames.

        A detection must appear in at least `smoothing_min_hits` of the
        last `smoothing_buffer_size` frames to be confirmed. Uses a LOW
        IoU threshold (0.15) to tolerate bbox shifts from person movement.
        """
        buffer = self.detection_buffers.get(camera_id)
        if not buffer:
            return []

        # Single frame — return as-is
        if len(buffer) == 1:
            return buffer[0]

        latest = buffer[-1]
        confirmed = []

        for det in latest:
            hits = 1  # Always count the current frame
            for prev_frame in list(buffer)[:-1]:
                for prev_det in prev_frame:
                    if prev_det["class_id"] == det["class_id"]:
                        iou = self._calculate_iou(det["bbox"], prev_det["bbox"])
                        if iou > self.smoothing_iou:
                            hits += 1
                            break

            # Be lenient in early frames, stricter once buffer fills up
            min_hits = 1 if len(buffer) < 3 else self.smoothing_min_hits
            if hits >= min_hits:
                confirmed.append(det)

        return confirmed

    @staticmethod
    def _calculate_iou(bbox1: list, bbox2: list) -> float:
        """Calculate IoU between two bounding boxes [x1, y1, x2, y2]."""
        x1 = max(bbox1[0], bbox2[0])
        y1 = max(bbox1[1], bbox2[1])
        x2 = min(bbox1[2], bbox2[2])
        y2 = min(bbox1[3], bbox2[3])

        intersection = max(0, x2 - x1) * max(0, y2 - y1)
        area1 = (bbox1[2] - bbox1[0]) * (bbox1[3] - bbox1[1])
        area2 = (bbox2[2] - bbox2[0]) * (bbox2[3] - bbox2[1])
        union = area1 + area2 - intersection

        return intersection / union if union > 0 else 0

    def _draw_detections(self, frame: np.ndarray, detections: List[dict]) -> np.ndarray:
        """Draw styled detection boxes and labels on frame.

        Style: colored rectangle + filled label background + white text.
        Colors: Green=Helmet, Red=No Helmet, Orange=Worker.
        """
        annotated = frame.copy()

        for det in detections:
            x1, y1, x2, y2 = det["bbox"]
            cls_id = det["class_id"]
            cls_name = det["class_name"]
            conf = det["confidence"]
            color = self.CLASS_COLORS.get(cls_id, (255, 255, 255))

            h, w = annotated.shape[:2]
            x1 = max(0, min(x1, w - 1))
            y1 = max(0, min(y1, h - 1))
            x2 = max(0, min(x2, w - 1))
            y2 = max(0, min(y2, h - 1))

            # Detection box
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 3)

            # Label with background
            label = f"{cls_name} {conf:.0%}"
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.55
            thickness = 2
            (text_w, text_h), baseline = cv2.getTextSize(
                label, font, font_scale, thickness
            )

            label_y = max(y1 - 6, text_h + 4)
            cv2.rectangle(
                annotated,
                (x1, label_y - text_h - 4),
                (x1 + text_w + 6, label_y + 2),
                color,
                -1,
            )
            cv2.putText(
                annotated, label, (x1 + 3, label_y - 2),
                font, font_scale, (255, 255, 255), thickness, cv2.LINE_AA,
            )

        return annotated

    def get_stats(self) -> dict:
        """Get detection statistics for dashboard API."""
        total = 0
        by_camera: Dict[str, dict] = {}
        for cam_id, dets in self.last_detections.items():
            count = len(dets)
            total += count
            by_camera[cam_id] = {
                "total": count,
                "no_helmet": sum(1 for d in dets if d["class_id"] == 1),
                "helmet": sum(1 for d in dets if d["class_id"] == 0),
                "worker": sum(1 for d in dets if d["class_id"] == 2),
            }
        return {"total_detections": total, "cameras": by_camera}