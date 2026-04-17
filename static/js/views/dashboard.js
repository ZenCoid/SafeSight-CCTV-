import { state, subscribe } from '../api.js';
import { openFullscreen } from '../app.js';

export default function render(container) {
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

        <div class="bento-grid" id="dash-grid"></div>
    `;

    const grid = document.getElementById('dash-grid');

    // Create cards once
    state.cameras.forEach(cam => {
        const div = document.createElement('div');
        div.className = 'camera-card';
        div.id = `card-${cam.id}`;
        div.innerHTML = `
            <img src="/stream/${cam.id}" alt="Stream" class="camera-feed" onerror="this.style.opacity='0'" onload="this.style.opacity='0.85'">
            <div class="camera-overlay">
                <div class="camera-header">
                    <span class="camera-name">${cam.name}</span>
                    <span class="status-dot live" id="dot-${cam.id}"></span>
                </div>
                <div class="camera-footer">
                    <span class="camera-tag" id="fps-${cam.id}">-- FPS</span>
                    <span class="camera-tag" style="background:var(--color-blue-glow);color:#fff">AI ON</span>
                </div>
            </div>
        `;
        div.onclick = () => openFullscreen(cam.id);
        grid.appendChild(div);
    });

    const updateView = (currentState) => {
        // Update stats
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

        // Update grid
        if (currentState.status && currentState.status.cameras) {
            currentState.cameras.forEach(cam => {
                const s = currentState.status.cameras[cam.id];
                if (!s) return;
                const dot = document.getElementById(`dot-${cam.id}`);
                const fps = document.getElementById(`fps-${cam.id}`);
                const card = document.getElementById(`card-${cam.id}`);
                
                if (dot) {
                    dot.className = `status-dot ${s.connected ? 'live' : 'offline'}`;
                }
                if (fps) {
                    fps.textContent = s.connected ? `${s.fps} FPS` : 'OFFLINE';
                }
                if (card) {
                    // Just a mock way to show alert on card
                    // You'd ideally know which camera threw the violation
                }
            });
        }
    };

    updateView(state);
    return subscribe(updateView);
}
