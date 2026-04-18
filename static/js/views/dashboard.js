import { state, subscribe } from '../api.js';

export default function render(container) {
    const firstCam = state.cameras[0];
    let activeCamId = firstCam ? firstCam.id : null;

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
                <button class="cam-btn ${cam.id === activeCamId ? 'active' : ''}" data-cam="${cam.id}">
                    <span class="status-dot live" id="sel-dot-${cam.id}"></span>
                    ${cam.name}
                    <span class="cam-btn-fps" id="sel-fps-${cam.id}">--</span>
                </button>
            `).join('')}
        </div>

        <div class="single-view" id="single-view">
            <div class="feed-container" id="feed-container">
                <img id="main-feed" src="${activeCamId ? `/stream/${activeCamId}` : ''}" class="feed-img">
                <div class="feed-controls" id="feed-controls">
                    <div class="feed-info">
                        <span class="status-dot live"></span>
                        <span class="feed-name" id="feed-name">${firstCam?.name || 'Select Camera'}</span>
                        <span class="camera-tag" id="feed-fps">-- FPS</span>
                        <span class="camera-tag" style="background:var(--color-blue-glow);color:#fff">AI ON</span>
                    </div>
                    <button class="btn btn-primary" id="fs-btn">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="15 3 21 3 21 9"></polyline><polyline points="9 21 3 21 3 15"></polyline><line x1="21" y1="3" x2="14" y2="10"></line><line x1="3" y1="21" x2="10" y2="14"></line></svg>
                        Fullscreen
                    </button>
                </div>
            </div>
        </div>
    `;

    // ─── Camera Switching ──────────────────────────
    function switchCamera(camId) {
        if (camId === activeCamId) return;
        activeCamId = camId;

        // Update buttons
        container.querySelectorAll('.cam-btn').forEach(b => {
            b.classList.toggle('active', b.dataset.cam === camId);
        });

        // Destroy old img, create new one (MJPEG can't switch src on active stream)
        const feedContainer = document.getElementById('feed-container');
        const oldImg = document.getElementById('main-feed');
        if (oldImg) oldImg.remove();

        const newImg = document.createElement('img');
        newImg.id = 'main-feed';
        newImg.className = 'feed-img';
        newImg.src = `/stream/${camId}`;
        newImg.onerror = () => { newImg.style.opacity = '0'; };
        newImg.onload = () => { newImg.style.opacity = '1'; };
        feedContainer.insertBefore(newImg, feedContainer.firstChild);

        // Update info
        const cam = state.cameras.find(c => c.id === camId);
        document.getElementById('feed-name').textContent = cam?.name || camId;
    }

    container.querySelectorAll('.cam-btn').forEach(btn => {
        btn.addEventListener('click', () => switchCamera(btn.dataset.cam));
    });

    // ─── Fullscreen (Browser Fullscreen API) ───────
    document.getElementById('fs-btn').addEventListener('click', () => {
        const el = document.getElementById('feed-container');
        if (el.requestFullscreen) {
            el.requestFullscreen();
        } else if (el.webkitRequestFullscreen) {
            el.webkitRequestFullscreen();
        } else if (el.msRequestFullscreen) {
            el.msRequestFullscreen();
        }
    });

    // ─── Stats Update ──────────────────────────────
    const updateView = (currentState) => {
        if (currentState.stats) {
            document.getElementById('dash-stat-online').textContent = `${currentState.stats.cameras_online || 0} / ${currentState.cameras.length}`;
            if (currentState.stats.detection) {
                document.getElementById('dash-stat-helmet').textContent = currentState.stats.detection.helmet_count || 0;
                document.getElementById('dash-stat-violations').textContent = currentState.stats.detection.violations || 0;
            }
            if (currentState.stats.violations) {
                document.getElementById('dash-stat-today').textContent = currentState.stats.violations.total_today || 0;
            }
        }

        // Update selector bar dots and FPS
        if (currentState.status && currentState.status.cameras) {
            currentState.cameras.forEach(cam => {
                const s = currentState.status.cameras[cam.id];
                if (!s) return;
                const dot = document.getElementById(`sel-dot-${cam.id}`);
                const fps = document.getElementById(`sel-fps-${cam.id}`);
                if (dot) {
                    dot.className = `status-dot ${s.connected ? 'live' : 'offline'}`;
                }
                if (fps) {
                    fps.textContent = s.connected ? `${s.fps}` : 'OFF';
                }
            });

            // Update feed FPS for active camera
            const activeStatus = currentState.status.cameras[activeCamId];
            if (activeStatus) {
                document.getElementById('feed-fps').textContent = activeStatus.connected ? `${activeStatus.fps} FPS` : 'OFFLINE';
            }
        }
    };

    updateView(state);
    return subscribe(updateView);
}