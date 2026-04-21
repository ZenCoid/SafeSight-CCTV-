import { state, subscribe } from '../api.js';

export default function render(container) {
    const firstCam = state.cameras[0];
    let activeCamId = firstCam ? firstCam.id : null;
    let isWebcam = !firstCam; // default to webcam if no CCTV cameras

    container.innerHTML = `
        <div class="stats-row">
            <div class="glass-panel stat-box">
                <div style="display:flex;align-items:center;gap:12px;color:var(--text-secondary)">
                    <div class="stat-icon-wrapper" style="background:var(--color-blue-glow);color:var(--color-blue)">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"></path><circle cx="12" cy="13" r="4"></circle></svg>
                    </div>
                    <span style="font-size:12px;text-transform:uppercase;letter-spacing:1px;font-weight:600">Online</span>
                </div>
                <div class="stat-value" id="dash-stat-online">--</div>
            </div>
            <div class="glass-panel stat-box">
                <div style="display:flex;align-items:center;gap:12px;color:var(--text-secondary)">
                    <div class="stat-icon-wrapper" style="background:var(--color-green-glow);color:var(--color-green)">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 11-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>
                    </div>
                    <span style="font-size:12px;text-transform:uppercase;letter-spacing:1px;font-weight:600">Helmets</span>
                </div>
                <div class="stat-value" id="dash-stat-helmet">--</div>
            </div>
            <div class="glass-panel stat-box">
                <div style="display:flex;align-items:center;gap:12px;color:var(--text-secondary)">
                    <div class="stat-icon-wrapper" style="background:var(--color-red-glow);color:var(--color-red)">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>
                    </div>
                    <span style="font-size:12px;text-transform:uppercase;letter-spacing:1px;font-weight:600">Violations</span>
                </div>
                <div class="stat-value" id="dash-stat-violations" style="color:var(--color-red)">--</div>
            </div>
            <div class="glass-panel stat-box">
                <div style="display:flex;align-items:center;gap:12px;color:var(--text-secondary)">
                    <div class="stat-icon-wrapper" style="background:rgba(168,85,247,0.2);color:#a855f7">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>
                    </div>
                    <span style="font-size:12px;text-transform:uppercase;letter-spacing:1px;font-weight:600">Today</span>
                </div>
                <div class="stat-value" id="dash-stat-today">--</div>
            </div>
        </div>

        <div class="camera-selector" id="camera-selector">
            ${state.cameras.map(cam => `
                <button class="cam-btn ${cam.id === activeCamId && !isWebcam ? 'active' : ''}" data-cam="${cam.id}">
                    <span class="status-dot live" id="sel-dot-${cam.id}"></span>
                    ${cam.name}
                    <span class="cam-btn-fps" id="sel-fps-${cam.id}">--</span>
                </button>
            `).join('')}
            <div style="width:1px;height:28px;background:var(--bg-border);margin:0 4px;flex-shrink:0"></div>
            <button class="cam-btn ${isWebcam ? 'active' : ''}" id="webcam-btn" style="${isWebcam ? 'background:rgba(168,85,247,0.15);color:#a855f7;border-color:#a855f7;' : ''}">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="color:#a855f7;flex-shrink:0"><rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect><line x1="8" y1="21" x2="16" y2="21"></line><line x1="12" y1="17" x2="12" y2="21"></line></svg>
                Webcam
            </button>
        </div>

        <div class="single-view" id="single-view">
            <div class="feed-container" id="feed-container">
                <img id="main-feed" src="${isWebcam ? '/stream/webcam' : (activeCamId ? `/stream/${activeCamId}` : '')}" class="feed-img" onerror="this.style.display='none'">
                <div id="webcam-error" style="${isWebcam ? 'display:none;' : 'display:none;'}position:absolute;inset:0;display:none;flex-direction:column;align-items:center;justify-content:center;gap:12px;color:var(--text-secondary);background:rgba(0,0,0,0.9);">
                    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="opacity:0.5"><rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect><line x1="8" y1="21" x2="16" y2="21"></line><line x1="12" y1="17" x2="12" y2="21"></line><line x1="1" y1="1" x2="23" y2="23"></line></svg>
                    <div style="font-weight:600;font-size:14px">Webcam Not Available</div>
                    <div style="font-size:12px;opacity:0.6">Make sure no other app is using the webcam</div>
                </div>
                <div class="feed-controls" id="feed-controls">
                    <div class="feed-info">
                        <span class="status-dot live" id="feed-dot"></span>
                        <span class="feed-name" id="feed-name">${isWebcam ? 'Webcam' : (firstCam?.name || 'No Camera')}</span>
                        <span class="camera-tag" id="feed-fps">-- FPS</span>
                        <span class="camera-tag" id="feed-source-tag" style="background:${isWebcam ? 'rgba(168,85,247,0.3)' : 'var(--color-blue-glow)'};color:#fff">${isWebcam ? 'WEBCAM' : 'CCTV'}</span>
                        <span class="camera-tag" style="background:var(--color-green-glow);color:#fff">AI ON</span>
                    </div>
                    <button class="btn btn-primary" id="fs-btn">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="15 3 21 3 21 9"></polyline><polyline points="9 21 3 21 3 15"></polyline><line x1="21" y1="3" x2="14" y2="10"></line><line x1="3" y1="21" x2="10" y2="14"></line></svg>
                        Fullscreen
                    </button>
                </div>
            </div>
        </div>
    `;

    // ─── Feed Elements ────────────────────────────
    const mainFeed = document.getElementById('main-feed');
    const feedName = document.getElementById('feed-name');
    const feedSourceTag = document.getElementById('feed-source-tag');
    const webcamBtn = document.getElementById('webcam-btn');
    const webcamError = document.getElementById('webcam-error');

    // ─── Camera Switching ──────────────────────────
    function switchToCctv(camId) {
        isWebcam = false;
        activeCamId = camId;

        // Update buttons
        container.querySelectorAll('.cam-btn:not(#webcam-btn)').forEach(b => {
            b.classList.toggle('active', b.dataset.cam === camId);
            if (b.dataset.cam === camId) {
                b.style.background = '';
                b.style.color = '';
                b.style.borderColor = '';
            } else {
                b.style.background = '';
                b.style.color = '';
                b.style.borderColor = '';
            }
        });
        webcamBtn.classList.remove('active');
        webcamBtn.style.background = '';
        webcamBtn.style.color = '';
        webcamBtn.style.borderColor = '';

        // Switch feed
        mainFeed.style.display = '';
        webcamError.style.display = 'none';
        mainFeed.src = `/stream/${camId}`;

        // Update info
        const cam = state.cameras.find(c => c.id === camId);
        feedName.textContent = cam?.name || camId;
        feedSourceTag.textContent = 'CCTV';
        feedSourceTag.style.background = 'var(--color-blue-glow)';
    }

    function switchToWebcam() {
        isWebcam = true;
        activeCamId = null;

        // Update buttons
        container.querySelectorAll('.cam-btn:not(#webcam-btn)').forEach(b => {
            b.classList.remove('active');
            b.style.background = '';
            b.style.color = '';
            b.style.borderColor = '';
        });
        webcamBtn.classList.add('active');
        webcamBtn.style.background = 'rgba(168,85,247,0.15)';
        webcamBtn.style.color = '#a855f7';
        webcamBtn.style.borderColor = '#a855f7';

        // Switch feed
        mainFeed.style.display = '';
        webcamError.style.display = 'none';
        mainFeed.src = '/stream/webcam';

        // Update info
        feedName.textContent = 'Webcam';
        feedSourceTag.textContent = 'WEBCAM';
        feedSourceTag.style.background = 'rgba(168,85,247,0.3)';
    }

    // ─── Handle Webcam Stream Error ───────────────
    mainFeed.addEventListener('error', function() {
        if (isWebcam) {
            mainFeed.style.display = 'none';
            webcamError.style.display = 'flex';
        }
    });

    // ─── Bind CCTV Camera Buttons ─────────────────
    container.querySelectorAll('.cam-btn:not(#webcam-btn)').forEach(btn => {
        btn.addEventListener('click', () => {
            if (btn.dataset.cam) switchToCctv(btn.dataset.cam);
        });
    });

    // ─── Bind Webcam Button ───────────────────────
    webcamBtn.addEventListener('click', switchToWebcam);

    // ─── Fullscreen (Browser Fullscreen API) ───────
    document.getElementById('fs-btn').addEventListener('click', () => {
        const el = document.getElementById('feed-container');
        if (el.requestFullscreen) {
            el.requestFullscreen();
        } else if (el.webkitRequestFullscreen) {
            el.webkitRequestFullscreen();
        }
    });

    // ─── Stats Update ─────────────────────────────
    function updateStats() {
        if (!state.status || !state.status.cameras) return;

        // Online count
        const onlineCount = Object.values(state.status.cameras).filter(c => c.connected).length;
        const onlineEl = document.getElementById('dash-stat-online');
        if (onlineEl) onlineEl.textContent = onlineCount + ' / ' + state.cameras.length;

        // Per-camera FPS in selector
        state.cameras.forEach(cam => {
            const fpsEl = document.getElementById(`sel-fps-${cam.id}`);
            if (fpsEl) {
                const camStatus = state.status.cameras[cam.id] || {};
                fpsEl.textContent = (camStatus.fps || 0) + ' fps';
            }
            const dotEl = document.getElementById(`sel-dot-${cam.id}`);
            if (dotEl) {
                const camStatus = state.status.cameras[cam.id] || {};
                dotEl.className = `status-dot ${camStatus.connected ? 'live' : 'offline'}`;
            }
        });

        // Feed FPS (only for CCTV)
        if (!isWebcam && activeCamId) {
            const camStatus = state.status.cameras[activeCamId] || {};
            const feedFps = document.getElementById('feed-fps');
            if (feedFps) feedFps.textContent = (camStatus.fps || 0) + ' FPS';
        } else if (isWebcam) {
            const feedFps = document.getElementById('feed-fps');
            if (feedFps) feedFps.textContent = 'LIVE';
        }

        // Detections count
        const helmetEl = document.getElementById('dash-stat-helmet');
        if (helmetEl) helmetEl.textContent = state.stats.total_detections || 0;

        // Violations count
        const violationEl = document.getElementById('dash-stat-violations');
        if (violationEl) violationEl.textContent = state.stats.total_violations || 0;

        // Today count
        const todayEl = document.getElementById('dash-stat-today');
        if (todayEl) todayEl.textContent = state.stats.today_violations || 0;
    }

    updateStats();
    return subscribe(updateStats);
}