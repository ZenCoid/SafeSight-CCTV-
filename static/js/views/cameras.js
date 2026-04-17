import { state, subscribe, toggleCameraDetection } from '../api.js';

export default function render(container) {
    container.innerHTML = `
        <div class="glass-panel" style="padding: 24px;">
            <h2 class="text-h2" style="margin-bottom: 24px;">Camera Management</h2>
            <div id="cam-list" style="display:flex;flex-direction:column;gap:16px;"></div>
        </div>
    `;

    const list = document.getElementById('cam-list');

    const updateView = () => {
        if (!state.cameras || !state.status.cameras) {
            list.innerHTML = '<p class="text-muted">Loading cameras...</p>';
            return;
        }

        list.innerHTML = state.cameras.map(cam => {
            const status = state.status.cameras[cam.id] || {};
            const enabled = state.status.detection_enabled ? state.status.detection_enabled[cam.id] : true;
            
            return `
                <div style="display:flex;justify-content:space-between;align-items:center;padding:16px;border:1px solid var(--bg-border);border-radius:var(--radius-sm);background:rgba(0,0,0,0.2)">
                    <div>
                        <div class="text-h2">${cam.name} <span class="text-small" style="font-weight:400;margin-left:8px">${cam.id} | IP: ${cam.ip || '---'}</span></div>
                        <div style="margin-top:8px;display:flex;align-items:center;gap:16px;">
                            <span style="font-size:12px;display:flex;align-items:center;gap:6px;">
                                <span class="status-dot ${status.connected ? 'live' : 'offline'}"></span>
                                ${status.connected ? 'Connected' : 'Disconnected'}
                            </span>
                            <span class="text-small">${status.fps || 0} FPS</span>
                        </div>
                    </div>
                    <div style="display:flex;gap:12px;">
                        <button class="btn btn-toggle-det" data-id="${cam.id}">
                            ${enabled ? 'Disable AI' : 'Enable AI'}
                        </button>
                        <button class="btn btn-reconnect" data-id="${cam.id}">Reconnect</button>
                    </div>
                </div>
            `;
        }).join('');

        // Bind events safely
        document.querySelectorAll('.btn-toggle-det').forEach(b => {
             b.onclick = () => toggleCameraDetection(b.dataset.id);
        });
        
        document.querySelectorAll('.btn-reconnect').forEach(b => {
             b.onclick = async () => {
                 b.textContent = '...';
                 await fetch(`/api/camera/reconnect/${b.dataset.id}`, { method: 'POST' });
                 b.textContent = 'Reconnect';
             };
        });
    };

    updateView();
    return subscribe(updateView);
}
