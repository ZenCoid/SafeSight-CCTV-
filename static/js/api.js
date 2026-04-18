const Config = {
    refreshRate: 2000,
    toastDuration: 4000
};

export const state = {
    cameras: [],
    status: {},
    stats: {},
    violations: [],
    listeners: new Set(),
};

export function subscribe(fn) {
    state.listeners.add(fn);
    return () => state.listeners.delete(fn);
}

function notify() {
    state.listeners.forEach(fn => fn(state));
}

export async function initApi() {
    try {
        const res = await fetch('/api/cameras');
        const data = await res.json();
        state.cameras = data.cameras || [];
    } catch (e) {
        console.error('Failed to load cameras:', e);
    }

    startPolling();
    setupWebSocket();
}

let pollInterval;
export function startPolling() {
    if (pollInterval) clearInterval(pollInterval);
    pollStatus();
    pollInterval = setInterval(pollStatus, Config.refreshRate);
}

async function pollStatus() {
    try {
        const [statusRes, statsRes] = await Promise.all([
            fetch('/api/status'),
            fetch('/api/stats'),
        ]);
        state.status = await statusRes.json();
        state.stats = await statsRes.json();
        notify();
    } catch (e) {}
}

export async function fetchViolations(limit=50, hours=24) {
    try {
        const res = await fetch(`/api/violations?limit=${limit}&hours=${hours}`);
        const data = await res.json();
        state.violations = data.violations || [];
        notify();
        return state.violations;
    } catch (e) {
        return [];
    }
}

export async function toggleCameraDetection(camId) {
    try {
        const res = await fetch(`/api/detection/toggle/${camId}`, { method: 'POST' });
        const data = await res.json();
        showToast('info', `Detection ${data.enabled ? 'ON' : 'OFF'} for ${camId}`);
        pollStatus();
        return data.enabled;
    } catch (e) {
        showToast('alert', 'Failed to toggle detection');
    }
}

export async function reconnectCamera(camId) {
    try {
        const res = await fetch(`/api/camera/reconnect/${camId}`, { method: 'POST' });
        const data = await res.json();
        showToast('info', `Reconnecting ${camId}...`);
        pollStatus();
        return data.success;
    } catch (e) {
        showToast('alert', 'Failed to reconnect');
    }
}

// ─── WebSocket (fixed: no interval leak on reconnect) ──────────
let wsInstance = null;
let wsPingInterval = null;

function setupWebSocket() {
    // Clean up previous WebSocket and its ping interval
    if (wsPingInterval) {
        clearInterval(wsPingInterval);
        wsPingInterval = null;
    }
    if (wsInstance) {
        try { wsInstance.close(); } catch {}
        wsInstance = null;
    }

    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${protocol}//${location.host}/ws/alerts`;

    try {
        const ws = new WebSocket(url);
        wsInstance = ws;

        ws.onopen = () => {
            // Start ping — store reference so we can clear it on reconnect
            wsPingInterval = setInterval(() => {
                if (ws.readyState === WebSocket.OPEN) {
                    ws.send('ping');
                }
            }, 30000);
        };

        ws.onmessage = (e) => {
            const data = JSON.parse(e.data);
            if (data.type !== 'pong') {
                if (data.type === 'violation' || data.snapshot_path) {
                    showToast('alert', `Violation Detected on ${data.camera_name || 'Camera'}`);
                }
                fetchViolations();
            }
        };

        ws.onclose = () => {
            // Clear ping, then reconnect after delay
            if (wsPingInterval) {
                clearInterval(wsPingInterval);
                wsPingInterval = null;
            }
            setTimeout(setupWebSocket, 5000);
        };

        ws.onerror = () => {};
    } catch (e) {
        setTimeout(setupWebSocket, 5000);
    }
}

export function showToast(type, message) {
    const container = document.getElementById('toast-container');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;

    const icons = {
        alert: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--color-red)" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>',
        info: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--color-blue)" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>',
    };

    const time = new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit' });

    toast.innerHTML = `
        ${icons[type] || icons.info}
        <div style="flex:1">
            <div style="font-weight:600;font-size:13px">${type === 'alert' ? 'Security Alert' : 'System Notice'}</div>
            <div style="color:var(--text-secondary);font-size:12px">${message}</div>
        </div>
        <span style="font-size:10px;color:var(--text-muted)">${time}</span>
    `;

    container.appendChild(toast);
    setTimeout(() => toast.classList.add('show'), 10);
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, Config.toastDuration);
}

export function formatTime(timestamp) {
    try {
        return new Date(timestamp + 'Z').toLocaleTimeString('en-US', {
            hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit',
        });
    } catch { return timestamp; }
}