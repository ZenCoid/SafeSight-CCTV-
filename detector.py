"""
SafeSight CCTV - YOLO Helmet/PPE Detector
Runs YOLO inference on camera frames, draws detection boxes,
and logs violations to the database with smart violation buffer.
"""
import cv2
import numpy as np
import time
from pathlib import Path

try:
    from ultralytics import YOLO
except ImportError:
    YOLO = None

from database import ViolationDB
from config import Config


class YOLODetector:
    def __init__(self, model_path="models/best.pt", confidence=0.45):
        self.model_path = model_path
        self.confidence = confidence
        self.model = None
        self.class_names = {0: 'Helmet', 1: 'No Helmet', 2: 'Worker'}
        self.class_colors = {
            0: (0, 200, 0),    # Green - Helmet
            1: (0, 0, 255),    # Red - No Helmet
            2: (255, 165, 0),  # Orange - Worker
        }
        self.frame_counts = {}
        self.last_detections = {}
        self.db = ViolationDB()

        # ─── Violation Buffer ──────────────────────────
        # Tracks consecutive "no helmet" frames per camera
        self.violation_counters = {}     # {camera_id: int}
        # Tracks last logged violation time per camera
        self.violation_cooldowns = {}    # {camera_id: float (timestamp)}

    def load_model(self) -> bool:
        """Load YOLO model. Returns True if successful."""
        model_file = Path(self.model_path)
        if not model_file.exists():
            print(f"[WARNING] Model file not found: {self.model_path}")
            print("[WARNING] Running without detection (camera feed only)")
            return False

        if YOLO is None:
            print("[WARNING] ultralytics not installed. Run: pip install ultralytics")
            return False

        try:
            self.model = YOLO(str(model_file))
            print(f"[OK] Model loaded: {self.model_path}")
            print(f"     Confidence threshold: {self.confidence}")
            print(f"     Detection interval: every {Config.DETECTION_INTERVAL} frames")
            print(f"     Violation threshold: {Config.VIOLATION_THRESHOLD} frames")
            print(f"     Violation cooldown: {Config.VIOLATION_COOLDOWN}s")
            return True
        except Exception as e:
            print(f"[ERROR] Failed to load model: {e}")
            return False

    def detect(self, camera_id, frame):
        """Run detection on a frame. Returns (annotated_frame, detections)."""
        self.frame_counts[camera_id] = self.frame_counts.get(camera_id, 0) + 1
        frame_num = self.frame_counts[camera_id]

        # Run detection every Nth frame (uses config value, not hardcoded)
        if self.model is not None and frame_num % Config.DETECTION_INTERVAL == 0:
            detections = self._run_inference(frame, camera_id)
            self.last_detections[camera_id] = detections
            if detections:
                annotated = self._draw_detections(frame, detections)
                return annotated, detections
            return frame, []
        else:
            # Use previous detections to keep boxes visible between inference
            prev = self.last_detections.get(camera_id, [])
            if prev:
                annotated = self._draw_detections(frame, prev)
                return annotated, prev
            return frame, []

    def _run_inference(self, frame, camera_id):
        """Run YOLO inference and return list of detection dicts."""
        try:
            results = self.model(frame, conf=self.confidence, verbose=False)
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
                    cls_name = self.class_names.get(cls_id, f"Class_{cls_id}")
                    detections.append({
                        'class_id': cls_id,
                        'class_name': cls_name,
                        'confidence': round(conf, 2),
                        'bbox': [int(x1), int(y1), int(x2), int(y2)]
                    })

                    # Track if any no-helmet was found in this frame
                    if cls_id == 1:
                        has_no_helmet = True

            # ─── Violation Buffer Logic ─────────────────────
            if has_no_helmet:
                # Increment consecutive no-helmet counter
                self.violation_counters[camera_id] = self.violation_counters.get(camera_id, 0) + 1
                counter = self.violation_counters[camera_id]

                # Check if threshold reached
                if counter >= Config.VIOLATION_THRESHOLD:
                    # Check cooldown
                    last_logged = self.violation_cooldowns.get(camera_id, 0)
                    now = time.time()
                    time_since = now - last_logged

                    if time_since >= Config.VIOLATION_COOLDOWN:
                        # Log the violation
                        self.db.log_violation(
                            camera_id=str(camera_id),
                            detection_type='no_helmet',
                            confidence=max(d['confidence'] for d in detections if d['class_id'] == 1)
                        )
                        self.violation_cooldowns[camera_id] = now
                        print(f"[VIOLATION] {camera_id} - No helmet detected (after {counter} frames)")
                    else:
                        # Cooldown active - don't log but keep counter
                        pass
            else:
                # No no-helmet in this frame - reset counter
                self.violation_counters[camera_id] = 0

            return detections
        except Exception as e:
            print(f"[ERROR] Inference failed: {e}")
            return []

    def _draw_detections(self, frame, detections):
        """Draw detection boxes and labels on frame. Optimized for 352x288 sub-stream."""
        annotated = frame.copy()

        for det in detections:
            x1, y1, x2, y2 = det['bbox']
            cls_id = det['class_id']
            cls_name = det['class_name']
            conf = det['confidence']
            color = self.class_colors.get(cls_id, (255, 255, 255))

            # Clamp bounding box to frame size
            h, w = annotated.shape[:2]
            x1 = max(0, min(x1, w - 1))
            y1 = max(0, min(y1, h - 1))
            x2 = max(0, min(x2, w - 1))
            y2 = max(0, min(y2, h - 1))

            # Thicker boxes (3px) for visibility on low-res 352x288
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 3)

            # Label background
            label = f"{cls_name} {conf:.0%}"
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.55
            thickness = 2
            (text_w, text_h), baseline = cv2.getTextSize(label, font, font_scale, thickness)

            label_y = max(y1 - 6, text_h + 4)
            cv2.rectangle(annotated, (x1, label_y - text_h - 4), (x1 + text_w + 6, label_y + 2), color, -1)
            cv2.putText(annotated, label, (x1 + 3, label_y - 2), font, font_scale, (255, 255, 255), thickness, cv2.LINE_AA)

        return annotated

    def get_stats(self):
        """Get detection statistics for dashboard."""
        total = 0
        by_camera = {}
        for cam_id, dets in self.last_detections.items():
            count = len(dets)
            total += count
            by_camera[cam_id] = {
                'total': count,
                'no_helmet': sum(1 for d in dets if d['class_id'] == 1),
                'helmet': sum(1 for d in dets if d['class_id'] == 0),
                'worker': sum(1 for d in dets if d['class_id'] == 2),
            }
        return {
            'total_detections': total,
            'cameras': by_camera
        }