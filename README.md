\# SafeSight CCTV - AI Safety Monitoring Platform



> Multi-camera construction site safety monitoring with YOLO helmet detection,

> CLAHE preprocessing, temporal smoothing, real-time WebSocket alerts, and Gmail notifications.



\## Quick Start



\### 1. Setup



```bash

cd safesight-cctv



\# Create virtual environment

python -m venv venv

venv\\Scripts\\activate        # Windows

source venv/bin/activate      # macOS/Linux



\# Install dependencies

pip install -r requirements.txt

```



\### 2. Configure



```bash

\# Copy camera config (edit with your NVR details)

copy cameras.json.example cameras.json     # Windows

cp cameras.json.example cameras.json       # macOS/Linux



\# Copy environment config (edit with your settings)

copy .env.example .env

```



\*\*Minimum .env changes:\*\*

```env

SMTP\_EMAIL=your\_email@gmail.com

SMTP\_PASSWORD=your\_16\_char\_app\_password

SMTP\_TO=your\_email@gmail.com

SMTP\_ENABLED=true

```



\### 3. Copy your model weights

```bash

\# Place your trained YOLO weights in weights/

\# weights/best.pt

```



\### 4. Run



```bash

\# Development (with auto-reload)

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000



\# Production

python -m app.main

```



\### 5. Open



\- \*\*Dashboard:\*\* http://localhost:8000

\- \*\*Webcam:\*\* http://localhost:8000/stream/webcam

\- \*\*Camera:\*\* http://localhost:8000/stream/cam1



\## Project Structure



```

safesight-cctv/

├── app/

│   ├── main.py              # FastAPI app, lifespan, middleware

│   ├── config.py            # Pydantic Settings + cameras.json

│   ├── routes/

│   │   ├── cameras.py       # Camera CRUD, toggle, reconnect

│   │   ├── stream.py        # MJPEG streams (webcam + cameras)

│   │   ├── violations.py    # Violation history + test alert

│   │   └── status.py        # System status + statistics

│   ├── core/

│   │   ├── camera.py        # Threaded RTSP camera with upscaling

│   │   ├── detector.py      # YOLO detection with LAB CLAHE + smoothing

│   │   └── violation.py     # Violation buffer/cooldown tracker

│   ├── services/

│   │   ├── alert\_service.py # Gmail SMTP with inline images

│   │   └── storage\_service.py # Snapshot save with annotations

│   ├── db/

│   │   └── database.py      # SQLite with WAL mode

│   └── websocket/

│       └── alerts.py        # Real-time WebSocket push

├── static/                   # Frontend SPA (HTML/CSS/JS)

├── cameras.json              # Camera definitions

├── weights/best.pt           # YOLO model weights

├── violations/               # Saved violation snapshots

├── network\_diagnostic.py     # RTSP/network diagnostic tool

├── requirements.txt

├── .env.example

├── Dockerfile

└── docker-compose.yml

```



\## API Endpoints



| Method | Endpoint | Description |

|--------|----------|-------------|

| GET | `/api/cameras` | Camera list with status |

| GET | `/api/status` | Full system status |

| GET | `/api/stats` | Aggregate statistics |

| GET | `/api/violations` | Violation history |

| POST | `/api/violations/send\_test` | Send test email alert |

| POST | `/api/detection/toggle/{id}` | Toggle detection per camera |

| POST | `/api/camera/reconnect/{id}` | Reconnect camera |

| POST | `/api/camera/reconnect\_all` | Reconnect all cameras |

| GET | `/stream/webcam` | Webcam MJPEG stream |

| GET | `/stream/{camera\_id}` | Camera MJPEG stream |

| WS | `/ws/alerts` | Real-time violation alerts |



\## Detection Parameters



| Parameter | Default | Purpose |

|-----------|---------|---------|

| `THRESHOLD\_HELMET` | 0.35 | Helmet detection sensitivity |

| `THRESHOLD\_NO\_HELMET` | 0.20 | No Helmet detection (lenient for safety) |

| `THRESHOLD\_WORKER` | 0.25 | Worker/person detection |

| `CLAHE\_CLIP\_LIMIT` | 2.0 | Contrast enhancement (LAB color space) |

| `FRAME\_UPSCALE` | true | Upscale small CCTV frames to 720px |

| `YOLO\_IMGSZ` | 1280 | YOLO input resolution |

| `SMOOTHING\_BUFFER\_SIZE` | 5 | Frames for temporal smoothing |

| `VIOLATION\_THRESHOLD` | 5 | Frames before alert triggers |

| `VIOLATION\_COOLDOWN` | 30 | Seconds between alerts |



\## Docker



```bash

docker-compose up --build

```



\## Diagnostic Tool



```bash

python network\_diagnostic.py

```



Tests RTSP connectivity, frame rates, bandwidth, and encoding speed.

