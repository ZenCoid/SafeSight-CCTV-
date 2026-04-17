---
name: safesight-cctv
description: Specialized knowledge for building, debugging, and improving the SafeSight AI CCTV helmet detection system. Covers YOLO inference, RTSP streaming, OpenCV video processing, and FastAPI MJPEG streaming architecture. Use when working on detector, camera, or streaming code.
version: 1.0.0
author: SafeSight Team
tags:
  - cctv
  - yolo
  - rtsp
  - opencv
  - fastapi
  - surveillance
  - ppe-detection
---

# SafeSight CCTV - Domain Knowledge Skill

## Overview

This skill provides specialized knowledge for the SafeSight AI CCTV system — a real-time multi-camera helmet/PPE detection system. Use this when working on YOLO inference, RTSP camera connections, OpenCV video processing, MJPEG streaming, or the FastAPI backend.

## YOLO Detection Best Practices

### Model Loading
- Always use `YOLO(model_path)` from the `ultralytics` package, not raw PyTorch
- Load the model ONCE at startup, reuse for all frames
- Never load the model inside the frame processing loop
- Model file is `models/best.pt` — YOLOv11n custom trained

### Inference Pattern
```python
# Run inference every 3rd frame (not every frame)
if frame_count % 3 == 0:
    results = model(frame, conf=0.45, verbose=False)
    # Parse results
    for result in results:
        boxes = result.boxes
        if boxes is None:
            continue
        for box in boxes:
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int)
            conf = float(box.conf[0])
            cls_id = int(box.cls[0])

# On non-inference frames, reuse previous detections for persistent boxes
```

### Drawing Detection Boxes
- Always clamp bounding boxes to frame dimensions: `x = max(0, min(x, w-1))`
- Use 3px line thickness for 352x288 sub-stream (1px is invisible at this resolution)
- Font scale 0.55 with thickness 2 for readable labels
- Label format: `"ClassName XX%"` (e.g., `"No Helmet 87%"`)
- Draw label background rectangle before text for readability
- Class colors: Green=Helmet, Red=No Helmet, Orange=Worker

### Common YOLO Pitfalls
- `result.boxes` can be `None` — always check before iterating
- Box coordinates come as tensors — call `.cpu().numpy().astype(int)` before using
- Confidence values are tensors — call `float()` to convert
- Never call `.verbose(True)` in production — floods the terminal
- Always wrap inference in try/except — model can crash on corrupt frames

## RTSP Camera Connection

### Dahua NVR Specifics
- 6 cameras share ONE IP address, differentiated by channel number
- RTSP URL format: `rtsp://user:encoded_pass@ip:port/cam/realmonitor?channel=N&subtype=S`
- `subtype=0` = main stream (1080p+), `subtype=1` = sub stream (352x288)
- Password with special chars (like `@@`) MUST be URL-encoded via `urllib.parse.quote(pwd, safe='')`
- Force TCP transport: `os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"`

### Threaded Frame Grabbing Pattern
```python
class ThreadedCamera:
    def __init__(self, rtsp_url):
        self.cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
        self.thread = threading.Thread(target=self._grab_frames, daemon=True)
        self.latest_frame = None
        self.connected = False

    def _grab_frames(self):
        while self.running:
            ret, frame = self.cap.read()
            if ret:
                self.latest_frame = frame
                self.connected = True
            else:
                self.connected = False
                time.sleep(1)  # Wait before retry
                self.cap.release()
                self.cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)

    def get_frame(self):
        return self.latest_frame.copy() if self.latest_frame is not None else None
```

### Common RTSP Pitfalls
- OpenCV defaults to UDP — Dahua NVRs need TCP (force via env var)
- `cv2.VideoCapture` blocks if URL is wrong — always test in a thread
- Camera disconnections are NORMAL — always implement auto-reconnect
- Frame resolution: check with `cap.get(cv2.CAP_PROP_FRAME_WIDTH)` after connecting
- Never call `cap.read()` from multiple threads — use one reader thread, share frame via variable

## MJPEG Streaming Architecture

### How It Works
```
Browser <── HTTP multipart/x-mixed-replace <── FastAPI StreamingResponse
                                                    │
                                              For each frame:
                                              1. Grab from camera thread
                                              2. Run YOLO detection
                                              3. Draw boxes on frame
                                              4. Encode as JPEG
                                              5. Yield as MJPEG boundary
```

### MJPEG Response Format
```python
def generate():
    while True:
        frame = camera.get_frame()
        if frame is None:
            # Return "no signal" placeholder
            time.sleep(0.5)
            continue

        annotated = detector.detect(camera_id, frame)

        _, jpeg = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 70])
        yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n"
        time.sleep(1.0 / target_fps)
```

### Performance Tips
- JPEG quality 70 for sub-stream grid, 90 for HD fullscreen
- Sub-stream at 352x288 = ~5-10KB per frame = smooth on local network
- HD stream at 1080p = ~50-100KB per frame = may need throttling
- Never run inference in the streaming generator thread — run in camera thread or separate worker
- Use `cv2.imencode` not `cv2.imwrite` — much faster for in-memory encoding

## FastAPI + OpenCV Integration

### Critical Import Checklist
Before writing any code that uses OpenCV functions, verify these imports exist:
```python
import cv2          # For FONT_HERSHEY_SIMPLEX, rectangle, putText, imencode, VideoCapture
import numpy as np  # For np.zeros, array operations
import os           # For os.environ (RTSP transport setting)
```

### Startup Sequence (Order Matters)
```
1. Load .env configuration
2. Create output directories (snapshots/)
3. Start sub-stream cameras (6 threads)
4. Load YOLO model (can take 5-10 seconds)
5. Initialize database
6. Start uvicorn server
```

### Shutdown Sequence
```
1. Stop all HD cameras first (they use more bandwidth)
2. Stop all sub-stream cameras
3. Close database connection
4. Exit
```

## SQLite Database Schema

```sql
CREATE TABLE violations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,           -- "YYYY-MM-DD HH:MM:SS"
    camera_id TEXT DEFAULT '',         -- "cam1", "cam2", etc.
    camera_name TEXT DEFAULT '',       -- "Camera 1", "Camera 2", etc.
    camera_ip TEXT DEFAULT '',         -- "192.168.100.18"
    detection_type TEXT NOT NULL,      -- "no_helmet", "helmet", "worker"
    confidence REAL NOT NULL,          -- 0.0 to 1.0
    snapshot_path TEXT,                -- "snapshots/violation_123.jpg"
    reviewed INTEGER DEFAULT 0,        -- 0=unreviewed, 1=reviewed
    notes TEXT DEFAULT ''              -- Human notes
);
```

## Debugging Checklist

When the system crashes or behaves unexpectedly:

1. **Black screen on all cameras** → Check NVR is reachable: `ping 192.168.100.18`
2. **Black screen on one camera** → Check channel number in cameras.json, check physical cable
3. **`NameError: name 'cv2' is not defined`** → Add `import cv2` at top of the file
4. **`NameError: name 'os' is not defined`** → Add `import os` at top of the file
5. **`ImportError: cannot import name 'X'`** → Check the actual class/function name in the source file
6. **`TypeError: unexpected keyword argument`** → Check parameter names match between caller and callee
7. **`AttributeError: object has no attribute`** → Check method exists on the class, not just assumed
8. **401 Unauthorized on RTSP** → Password is wrong or URL-encoding is broken
9. **Detection boxes not visible** → Check line thickness (min 2px), font scale (min 0.5), and box clamping
10. **High CPU usage** → Reduce STREAM_FPS, increase detection interval (every 4th or 5th frame)
11. **WebSocket not receiving alerts** → Check browser console for WS errors, verify endpoint path
12. **DeprecationWarning: on_event** → Plan migration to lifespan handler (not urgent)

## Resolution-Specific Optimizations

### Sub-stream (352x288) — Grid View
- Box line width: 3px
- Font scale: 0.55
- Font thickness: 2
- JPEG quality: 70
- These values are the MINIMUM for visibility — do NOT reduce

### HD Stream (1080p+) — Fullscreen View
- Box line width: 2px
- Font scale: 0.7
- Font thickness: 2
- JPEG quality: 90
- Can also add filled semi-transparent boxes for a more polished look