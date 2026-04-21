"""
SafeSight CCTV - YOLO Helmet/PPE Detector
Runs YOLO inference on camera frames, draws detection boxes,
and logs violations to the database with smart violation buffer.

Enhanced for CCTV footage:
  - CLAHE contrast preprocessing (shadows/overexposure fix)
  - YOLO 960 input resolution (better small object detection)
  - Class-specific confidence thresholds (strict helmet, lenient no-helmet)
  - Temporal detection smoothing with movement-tolerant IoU
"""
import cv2
import numpy as np
import time
import os
from pathlib import Path
from collections import deque
from datetime import datetime

try:
    from ultralytics import YOLO
except ImportError:
    YOLO = None

from database import ViolationDB
from config import Config
from email_sender import send_violation_alert


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

        # ─── Violation Buffer ──────────────────────────────
        self.violation_counters = {}
        self.violation_cooldowns = {}

        # ─── Temporal Smoothing ────────────────────────────
        self.detection_buffers = {}
        self.smoothing_buffer_size = Config.SMOOTHING_BUFFER_SIZE
        self.smoothing_min_hits = Config.SMOOTHING_MIN_HITS

        # ─── CLAHE Preprocessor ────────────────────────────
        self.clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)) \
            if Config.CLAHE_ENABLED else None

        # ─── Class-Specific Confidence Thresholds ─────────
        # Helmet 0.35: real hard hats score 0.40+, caps score 0.10-0.25,
        #              occasional cap edge case at 0.30-0.34 gets blocked
        # No Helmet 0.20: lenient for safety — catch violations reliably
        # Worker 0.25: moderate
        self.class_confidence = {
            0: 0.35,   # Helmet    — strict: blocks caps, allows real hard hats
            1: 0.20,   # No Helmet — lenient: safety priority
            2: 0.25,   # Worker    — moderate
        }

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
            print(f"     YOLO input size: {Config.YOLO_IMGSZ}")
            print(f"     Test-time augment: {Config.YOLO_AUGMENT}")
            print(f"     CLAHE preprocessing: {Config.CLAHE_ENABLED}")
            print(f"     Frame upscaling: {Config.FRAME_UPSCALE} (min {Config.MIN_FRAME_DIMENSION}px)")
            print(f"     Smoothing: {self.smoothing_buffer_size} frames / {self.smoothing_min_hits} min hits (IoU 0.15)")
            print(f"     Class thresholds: Helmet={self.class_confidence[0]}, No Helmet={self.class_confidence[1]}, Worker={self.class_confidence[2]}")
            print(f"     Detection interval: every {Config.DETECTION_INTERVAL} frames")
            print(f"     Violation threshold: {Config.VIOLATION_THRESHOLD} frames")
            print(f"     Violation cooldown: {Config.VIOLATION_COOLDOWN}s")
            return True
        except Exception as e:
            print(f"[ERROR] Failed to load model: {e}")
            return False

    def _preprocess_frame(self, frame):
        """Apply CLAHE contrast enhancement for CCTV footage.
        Converts to LAB color space, enhances the L (lightness) channel,
        and merges back. Helps detection in shadowy or overexposed areas."""
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

    def detect(self, camera_id, frame):
        """Run detection on a frame. Returns (annotated_frame, detections)."""
        self.frame_counts[camera_id] = self.frame_counts.get(camera_id, 0) + 1
        frame_num = self.frame_counts[camera_id]

        # Initialize smoothing buffer for this camera
        if camera_id not in self.detection_buffers:
            self.detection_buffers[camera_id] = deque(maxlen=self.smoothing_buffer_size)

        # Run detection every Nth frame (uses config value)
        if self.model is not None and frame_num % Config.DETECTION_INTERVAL == 0:
            raw_detections = self._run_inference(frame, camera_id)

            # Add raw detections to smoothing buffer
            self.detection_buffers[camera_id].append(raw_detections)

            # Get smoothed detections (stable across multiple frames)
            smoothed = self._smooth_detections(camera_id)
            self.last_detections[camera_id] = smoothed

            if smoothed:
                annotated = self._draw_detections(frame, smoothed)
                return annotated, smoothed
            return frame, []
        else:
            # Use previous smoothed detections to keep boxes visible between inference
            prev = self.last_detections.get(camera_id, [])
            if prev:
                annotated = self._draw_detections(frame, prev)
                return annotated, prev
            return frame, []

    def _run_inference(self, frame, camera_id):
        """Run YOLO inference with enhanced CCTV settings.
        Returns list of raw detection dicts (before smoothing)."""
        try:
            # Step 1: Preprocess frame for CCTV conditions
            enhanced = self._preprocess_frame(frame)

            # Step 2: Run YOLO with optimized parameters for CCTV
            results = self.model(
                enhanced,
                conf=0.10,
                imgsz=Config.YOLO_IMGSZ,
                augment=Config.YOLO_AUGMENT,
                iou=Config.YOLO_IOU,
                max_det=50,
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

                    # Step 3: Apply class-specific confidence threshold
                    cls_threshold = self.class_confidence.get(cls_id, 0.20)
                    if conf < cls_threshold:
                        continue

                    cls_name = self.class_names.get(cls_id, f"Class_{cls_id}")
                    detections.append({
                        'class_id': cls_id,
                        'class_name': cls_name,
                        'confidence': round(conf, 2),
                        'bbox': [int(x1), int(y1), int(x2), int(y2)]
                    })

                    if cls_id == 1:
                        has_no_helmet = True

            # ─── Violation Buffer Logic (based on RAW detections) ─────
            if has_no_helmet:
                self.violation_counters[camera_id] = self.violation_counters.get(camera_id, 0) + 1
                counter = self.violation_counters[camera_id]

                if counter >= Config.VIOLATION_THRESHOLD:
                    last_logged = self.violation_cooldowns.get(camera_id, 0)
                    now = time.time()
                    time_since = now - last_logged

                    if time_since >= Config.VIOLATION_COOLDOWN:
                        # ─── Save Snapshot ─────────────────────────
                        snapshot_path = self._save_snapshot(camera_id, frame, detections)

                        # ─── Log to Database ────────────────────────
                        max_conf = max(d['confidence'] for d in detections if d['class_id'] == 1)

                        # Get camera name from main.py camera_configs if available
                        cam_name = str(camera_id)
                        cam_ip = ''
                        try:
                            from main import camera_configs
                            if camera_id in camera_configs:
                                cam_name = camera_configs[camera_id].name
                                cam_ip = camera_configs[camera_id].ip
                        except ImportError:
                            pass

                        self.db.log_violation(
                            camera_id=str(camera_id),
                            camera_name=cam_name,
                            camera_ip=cam_ip,
                            detection_type='no_helmet',
                            confidence=max_conf,
                            snapshot_path=snapshot_path,
                        )
                        self.violation_cooldowns[camera_id] = now
                        print(f"[VIOLATION] {camera_id} - No helmet detected (after {counter} frames, conf={max_conf:.0%})")

                        # ─── Send Email Alert ───────────────────────
                        send_violation_alert(
                            camera_name=cam_name,
                            detection_type='no_helmet',
                            confidence=max_conf,
                            snapshot_path=snapshot_path,
                        )
                    else:
                        pass
            else:
                self.violation_counters[camera_id] = 0

            return detections
        except Exception as e:
            print(f"[ERROR] Inference failed: {e}")
            return []

    def _smooth_detections(self, camera_id):
        """Return detections that are stable across multiple recent frames.
        A detection must appear in at least `smoothing_min_hits` of the
        last `smoothing_buffer_size` frames to be considered confirmed.
        Uses a LOW IoU threshold (0.15) to tolerate bbox shifts from
        person movement between inference frames."""
        buffer = self.detection_buffers.get(camera_id)
        if not buffer:
            return []

        # If only 1 frame in buffer, return as-is (no smoothing possible yet)
        if len(buffer) == 1:
            return buffer[0]

        latest = buffer[-1]  # Current frame's detections
        confirmed = []

        for det in latest:
            hits = 1  # Always count the current frame
            for prev_frame in list(buffer)[:-1]:
                for prev_det in prev_frame:
                    if prev_det['class_id'] == det['class_id']:
                        iou = self._calculate_iou(det['bbox'], prev_det['bbox'])
                        if iou > 0.15:
                            hits += 1
                            break

            # Be lenient in early frames, stricter once buffer fills up
            min_hits = 1 if len(buffer) < 3 else self.smoothing_min_hits
            if hits >= min_hits:
                confirmed.append(det)

        return confirmed

    def _calculate_iou(self, bbox1, bbox2):
        """Calculate IoU (Intersection over Union) between two bounding boxes."""
        x1 = max(bbox1[0], bbox2[0])
        y1 = max(bbox1[1], bbox2[1])
        x2 = min(bbox1[2], bbox2[2])
        y2 = min(bbox1[3], bbox2[3])

        intersection = max(0, x2 - x1) * max(0, y2 - y1)
        area1 = (bbox1[2] - bbox1[0]) * (bbox1[3] - bbox1[1])
        area2 = (bbox2[2] - bbox2[0]) * (bbox2[3] - bbox2[1])
        union = area1 + area2 - intersection

        return intersection / union if union > 0 else 0

    def _draw_detections(self, frame, detections):
        """Draw detection boxes and labels on frame."""
        annotated = frame.copy()

        for det in detections:
            x1, y1, x2, y2 = det['bbox']
            cls_id = det['class_id']
            cls_name = det['class_name']
            conf = det['confidence']
            color = self.class_colors.get(cls_id, (255, 255, 255))

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
            (text_w, text_h), baseline = cv2.getTextSize(label, font, font_scale, thickness)

            label_y = max(y1 - 6, text_h + 4)
            cv2.rectangle(annotated, (x1, label_y - text_h - 4), (x1 + text_w + 6, label_y + 2), color, -1)
            cv2.putText(annotated, label, (x1 + 3, label_y - 2), font, font_scale, (255, 255, 255), thickness, cv2.LINE_AA)

        return annotated

    def _save_snapshot(self, camera_id: str, frame, detections: list) -> str:
        """Save an annotated snapshot of the frame with detection boxes.
        Returns the file path, or None if saving fails."""
        try:
            os.makedirs(Config.SNAPSHOT_DIR, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            filename = f"{camera_id}_{timestamp}.jpg"
            filepath = os.path.join(Config.SNAPSHOT_DIR, filename)

            # Draw detection boxes on a copy of the frame
            annotated = frame.copy()
            for det in detections:
                x1, y1, x2, y2 = det['bbox']
                cls_id = det['class_id']
                cls_name = det['class_name']
                conf = det['confidence']
                color = self.class_colors.get(cls_id, (255, 255, 255))

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
                (text_w, text_h), _ = cv2.getTextSize(label, font, font_scale, thickness)
                label_y = max(y1 - 6, text_h + 4)
                cv2.rectangle(annotated, (x1, label_y - text_h - 4), (x1 + text_w + 6, label_y + 2), color, -1)
                cv2.putText(annotated, label, (x1 + 3, label_y - 2), font, font_scale, (255, 255, 255), thickness, cv2.LINE_AA)

            # Add timestamp overlay
            ts_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cv2.putText(annotated, f"SafeSight AI | {camera_id} | {ts_text}",
                       (10, annotated.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)

            cv2.imwrite(filepath, annotated, [cv2.IMWRITE_JPEG_QUALITY, Config.SNAPSHOT_QUALITY])
            print(f"[SNAPSHOT] Saved: {filepath}")
            return filepath
        except Exception as e:
            print(f"[SNAPSHOT] Failed to save: {e}")
            return None

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