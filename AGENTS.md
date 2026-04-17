# SafeSight AI - AGENTS.md

> AI-powered CCTV helmet/PPE detection system with multi-camera RTSP streaming, YOLO inference, and real-time violation alerting.

---

## Project Overview

SafeSight AI is a real-time CCTV monitoring system that detects PPE (Personal Protective Equipment) violations using YOLO object detection across 6 IP cameras connected to a single Dahua NVR. It streams annotated video to a web dashboard and logs violations with WebSocket alert push notifications.

**Current deployment**: Local network (Windows, Python 3.11) at `D:\safesight-cctv\`
**Landing page**: https://safesight-ai.netlify.app/ (separate repo at `D:\sentinel\`)
**GitHub**: https://github.com/ZenCoid/safesight-ai (landing page only)

---

## Tech Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| Language | Python | 3.11 |
| Web Framework | FastAPI | Latest |
| ASGI Server | Uvicorn | Latest |
| AI Model | YOLOv11n (ultralytics) | Latest |
| Video Capture | OpenCV (cv2) | Latest |
| Database | SQLite3 | Built-in |
| Frontend | Vanilla HTML/CSS/JS | — |
| Video Streaming | MJPEG (multipart/x-mixed-replace) | — |
| Real-time Alerts | WebSocket | FastAPI built-in |

---

## Project Structure

```
D:\safesight-cctv\
├── main.py              # FastAPI server entry point
├── config.py            # Loads .env, cameras.json, builds RTSP URLs
├── camera.py            # ThreadedCamera - threaded RTSP frame grabber
├── detector.py          # YOLODetector - inference + bounding box drawing
├── database.py          # ViolationDB - SQLite violation logger
├── cameras.json         # 6 camera configs (same NVR IP, different channels)
├── .env                 # CAMERA_PASSWORD, CAMERA_IP, etc.
├── AGENTS.md            # THIS FILE - project rules for AI agents
├── models/
│   └── best.pt          # YOLOv11n custom trained model
├── static/
│   ├── index.html       # Dashboard - 3x2 camera grid, click for fullscreen
│   ├── style.css        # Dark security theme
│   └── app.js           # WebSocket alerts, live stats, camera controls
├── snapshots/           # Auto-created, violation screenshot images
└── violations.db        # Auto-created SQLite database
```

### File Responsibilities

- **main.py**: FastAPI app, routes, startup/shutdown lifecycle, MJPEG streaming, WebSocket alerts. This is the ORCHESTRATOR — it imports and coordinates all other modules. Do NOT change the interface/function signatures of other modules without checking main.py first.
- **config.py**: Reads `.env` via `python-dotenv`, loads `cameras.json`, provides `Config` class with all settings and `CameraConfig` dataclass for individual cameras. Builds RTSP URLs with proper password encoding via `urllib.parse.quote(pwd, safe='')`.
- **camera.py**: `ThreadedCamera` class — connects to RTSP in a background thread, continuously grabs frames. Must import `os`. Provides `start()`, `stop()`, `get_frame()`, `get_status()`, `connect()` methods.
- **detector.py**: `YOLODetector` class — loads YOLO model, runs inference every 3rd frame, draws detection boxes. Must import `cv2`. Constructor takes `model_path` and `confidence` params. Has `load_model()` (returns bool), `detect(camera_id, frame)` (returns tuple), `get_stats()` methods.
- **database.py**: `ViolationDB` class — SQLite operations. Constructor takes optional `db_path`. Has `log_violation()`, `get_violations()`, `get_stats()`, `clear_old_records()`, `close()` methods.
- **static/index.html**: Dashboard HTML — 3x2 grid of camera feeds, click any to open fullscreen. Contains sidebar stats, violation log, alert controls.
- **static/style.css**: Dark security theme. MUST be mobile-responsive. Grid layout for 6 cameras, fullscreen overlay for single camera view.
- **static/app.js**: Frontend logic — fetches `/api/status`, `/api/stats`, `/api/violations`. WebSocket connection to `/ws/alerts` for real-time notifications. Camera controls (reconnect, toggle detection).

---

## Camera Hardware Configuration

- **NVR**: Dahua DVR/NVR at `192.168.100.18`, port `554`
- **6 cameras share ONE IP**, differentiated by RTSP channel numbers (1-6)
- **Username**: `admin`
- **Password**: `admin123456@@` (MUST be URL-encoded as `admin123456%40%40` in RTSP URLs)
- **Transport**: TCP forced via `os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"`
- **Sub-stream (grid view)**: `subtype=1` → 352x288 resolution
- **HD stream (fullscreen)**: `subtype=0` → 1080p+ resolution
- **RTSP URL format**: `rtsp://admin:admin123456%40%40@192.168.100.18:554/cam/realmonitor?channel={1-6}&subtype={0 or 1}`

### cameras.json Format
```json
[
  {"id": "cam1", "name": "Camera 1", "ip": "192.168.100.18", "port": 554, "username": "admin", "channel": 1, "password": "admin123456@@"},
  {"id": "cam2", "name": "Camera 2", "ip": "192.168.100.18", "port": 554, "username": "admin", "channel": 2, "password": "admin123456@@"},
  {"id": "cam3", "name": "Camera 3", "ip": "192.168.100.18", "port": 554, "username": "admin", "channel": 3, "password": "admin123456@@"},
  {"id": "cam4", "name": "Camera 4", "ip": "192.168.100.18", "port": 554, "username": "admin", "channel": 4, "password": "admin123456@@"},
  {"id": "cam5", "name": "Camera 5", "ip": "192.168.100.18", "port": 554, "username": "admin", "channel": 5, "password": "admin123456@@"},
  {"id": "cam6", "name": "Camera 6", "ip": "192.168.100.18", "port": 554, "username": "admin", "channel": 6, "password": "admin123456@@"}
]
```

---

## AI Detection Details

- **Model**: YOLOv11n (ultralytics package) — custom trained, file: `models/best.pt`
- **Classes**: `{0: 'Helmet', 1: 'No Helmet', 2: 'Worker'}`
- **Confidence threshold**: 0.45 (configurable via `Config.CONFIDENCE_THRESHOLD`)
- **Detection frequency**: Every 3rd frame (balance between performance and smoothness)
- **Box colors**: Green `(0, 200, 0)` = Helmet, Red `(0, 0, 255)` = No Helmet, Orange `(255, 165, 0)` = Worker
- **Box thickness**: 3px (optimized for 352x288 sub-stream resolution — do NOT reduce below 2)
- **Font**: `cv2.FONT_HERSHEY_SIMPLEX`, scale 0.55, thickness 2 (optimized for small resolution)
- **Between-inference persistence**: When no inference runs on a frame, the PREVIOUS detections are redrawn so boxes don't flicker

---

## API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/` | Dashboard HTML |
| GET | `/stream/{camera_id}` | MJPEG sub-stream (grid view) |
| GET | `/hd/{camera_id}` | MJPEG HD stream (fullscreen, lazy connect) |
| POST | `/api/hd/stop/{camera_id}` | Stop HD stream to save resources |
| GET | `/cameras` | Camera list with connection status |
| GET | `/api/status` | Full system status (cameras + detection + HD) |
| GET | `/api/stats` | Detection + violation statistics |
| GET | `/api/violations` | Violation log (paginated, filterable by camera) |
| POST | `/api/detection/toggle/{camera_id}` | Enable/disable detection per camera |
| POST | `/api/camera/reconnect/{camera_id}` | Reconnect single camera |
| POST | `/api/camera/reconnect_all` | Reconnect all cameras |
| WS | `/ws/alerts` | Real-time violation alert push |

---

## Environment Variables (.env)

```
CAMERA_IP=192.168.100.18
CAMERA_PORT=554
CAMERA_USERNAME=admin
CAMERA_PASSWORD=admin123456@@
SERVER_HOST=0.0.0.0
SERVER_PORT=8000
MODEL_PATH=models/best.pt
CONFIDENCE_THRESHOLD=0.45
STREAM_FPS=15
JPEG_QUALITY=70
SNAPSHOT_DIR=snapshots
DB_PATH=violations.db
```

---

## Code Rules (CRITICAL — READ BEFORE CHANGING ANY CODE)

### 1. Import Safety (BUG-FREE GUARANTEE)
Every Python file MUST import everything it uses. Before writing any code, check EVERY function call and verify its import exists at the top of the file. Common mistakes we've hit:
- `detector.py` MUST have `import cv2` at the top (for `cv2.FONT_HERSHEY_SIMPLEX`, `cv2.rectangle`, etc.)
- `camera.py` MUST have `import os` at the top (for `os.environ`)
- `database.py` class is called `ViolationDB` (NOT `Database`)

### 2. Cross-Module Interface Contracts
These function signatures MUST match between files. Do NOT change them without updating ALL callers:

**detector.py → YOLODetector**:
```python
class YOLODetector:
    def __init__(self, model_path: str, confidence: float)  # NOTE: param is "confidence", NOT "conf"
    def load_model(self) -> bool                              # Called by main.py at startup
    def detect(self, camera_id, frame) -> tuple              # Returns (annotated_frame, detections_list)
    def get_stats(self) -> dict                               # Returns detection statistics
```

**database.py → ViolationDB**:
```python
class ViolationDB:
    def __init__(self, db_path: str = None)
    def log_violation(self, detection_type: str, confidence: float, camera_id: str = "", camera_name: str = "", camera_ip: str = "", snapshot_path: str = None) -> int
    def get_violations(self, limit: int = 50, offset: int = 0, hours: int = 24, camera_id: str = None) -> list
    def get_stats(self) -> dict
    def clear_old_records(self, days: int = 30)
    def close(self)
```

**camera.py → ThreadedCamera**:
```python
class ThreadedCamera:
    def __init__(self, camera_id: str, camera_name: str, rtsp_url: str)
    def start(self) -> bool
    def stop(self)
    def get_frame(self) -> np.ndarray | None
    def get_status(self) -> dict
    def connect(self) -> bool
```

### 3. Password URL Encoding
The `@@` in the password MUST be encoded as `%40%40` in RTSP URLs. Use `urllib.parse.quote(password, safe='')`. This is handled in `config.py` — do NOT hardcode RTSP URLs.

### 4. No Breaking Changes
When modifying any module, ensure ALL routes in `main.py` that reference it continue to work. Test by checking:
- Does `get_detector()` still create the detector correctly?
- Does `det.detect(camera_id, frame)` still return a tuple of (frame, detections)?
- Does `det.get_stats()` still return a dict?
- Does `det.load_model()` still exist and return bool?

---

## Tasks to Complete (In Priority Order)

### HIGH PRIORITY

1. **Fix Fullscreen CSS** — The fullscreen camera view (triggered by clicking a camera in the grid) has broken layout. The camera feed should fill the entire viewport with an overlay close button, camera name, and detection stats. Currently the layout is misaligned/broken in `style.css`. Ensure proper z-indexing, the fullscreen overlay sits above everything, the `<img>` or video element fills 100% width/height, and the close button (X) is positioned top-right and clearly visible.

2. **Mobile Responsive Dashboard** — The 3x2 grid must work on mobile screens. On small screens (< 768px), switch to 2x3 or 1-column layout. Sidebar stats should collapse into a hamburger menu or bottom sheet. All buttons must be touch-friendly (min 44px tap targets).

3. **Modernize Dashboard UI** — Improve the visual design while keeping the dark security theme:
   - Add glassmorphism cards with subtle blur effects
   - Smooth transitions when switching between grid and fullscreen
   - Pulsing red indicator for active violations
   - Camera status badges (online/offline/reconnecting)
   - Live FPS counter per camera
   - Animated connection status dots

### MEDIUM PRIORITY

4. **Deprecation Warning Fix** — Replace `@app.on_event("startup")` and `@app.on_event("shutdown")` with FastAPI lifespan event handler pattern.

5. **Error Resilience** — Add proper error handling in the MJPEG stream generator so one camera failure doesn't crash the entire server. Wrap all detection calls in try/except and fall back to raw (unannotated) frames.

6. **Violation Gallery** — Add a new page or modal that shows historical violation snapshots with timestamps, camera names, and confidence scores. Allow filtering by camera and date range.

### LOW PRIORITY / CREATIVE FREEDOM

7. **Sound Alerts** — Add optional browser notification sound when a violation is detected (toggleable by user).

8. **Camera Recording** — Add ability to record a camera stream to a local video file (MP4) for a specified duration. This should be on-demand, not continuous.

9. **Daily Report Generation** — Generate a daily PDF/HTML summary of all violations with timestamps, camera names, and snapshot images.

10. **Multi-language Support** — Add Urdu/English language toggle for the dashboard UI.

---

## What NOT to Change

- The YOLO model file (`models/best.pt`) — do NOT retrain or replace
- The class names `{0: 'Helmet', 1: 'No Helmet', 2: 'Worker'}` — these are tied to the trained model
- The landing page repo (`D:\sentinel\`) — completely separate project
- Camera hardware (NVR, wiring, physical setup) — not a software issue
- The RTSP URL format — specific to Dahua NVR protocol

---

## Testing Approach

Since this runs on a local network with physical cameras, traditional unit testing is limited. Instead:

1. **Test without cameras**: Comment out camera connections and verify the server starts, serves static files, and returns proper JSON from API endpoints
2. **Test with one camera**: Connect only one camera and verify detection works, violations are logged, WebSocket alerts fire
3. **Visual verification**: Open `http://localhost:8000` and check the 3x2 grid renders, detection boxes appear, fullscreen works
4. **Stress test**: Open multiple browser tabs to verify MJPEG streams handle concurrent viewers

---

## Git Conventions

- Commit messages: `type(scope): description` (e.g., `fix(detector): add missing cv2 import`)
- Types: `feat`, `fix`, `refactor`, `style`, `docs`, `chore`
- Scope: `detector`, `camera`, `database`, `config`, `dashboard`, `api`, `ui`

---

## Known Issues

1. **Camera wiring fault** — Intermittent connection drops due to physical cable issues. Software handles this with auto-reconnect, but expect occasional black screens.
2. **Model false positives** — Caps/hats are sometimes detected as helmets. This requires model retraining with better data — deferred to later.
3. **Fullscreen CSS broken** — Layout issues when clicking camera to go fullscreen. Needs CSS fix in `style.css`.
4. **Deprecation warnings** — `@app.on_event` is deprecated in newer FastAPI. Should migrate to lifespan pattern.

---

## Performance Targets

- Stream latency: < 500ms from camera to dashboard
- Detection FPS: > 10 FPS per camera on the local machine
- Dashboard load time: < 2 seconds initial load
- WebSocket alert latency: < 200ms from detection to browser notification
- Support 6 simultaneous camera streams on a standard Windows PC (i5/i7, 8-16GB RAM, no GPU required for YOLOv11n)