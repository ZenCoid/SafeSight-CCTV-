import { initApi, state } from './api.js';
import { Router } from './router.js';

document.addEventListener('DOMContentLoaded', async () => {
    // Clock
    function updateClock() {
        const now = new Date();
        document.getElementById('header-time').textContent = now.toLocaleTimeString('en-US', {
            hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit',
        });
        document.getElementById('header-date').textContent = now.toLocaleDateString('en-US', {
            weekday: 'short', month: 'short', day: 'numeric',
        });
    }
    updateClock();
    setInterval(updateClock, 250);

    // Sidebar Toggle
    document.getElementById('toggle-sidebar').addEventListener('click', () => {
        document.getElementById('sidebar').classList.toggle('collapsed');
    });

    // Init API
    await initApi();

    // Init Router
    const router = new Router();
    router.handleRoute();

    // Fullscreen Close & Hotkeys
    document.getElementById('fs-close').addEventListener('click', closeFullscreen);

    document.addEventListener('keydown', e => {
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
        if (e.key === 'Escape') closeFullscreen();
        if (e.key >= '1' && e.key <= '6') {
            const idx = parseInt(e.key) - 1;
            if (state.cameras[idx]) {
                openFullscreen(state.cameras[idx].id);
            }
        }
        if (e.key.toLowerCase() === 'g') router.navigate('/');
        if (e.key.toLowerCase() === 's' && !e.ctrlKey && !e.metaKey) document.getElementById('sidebar').classList.toggle('collapsed');
    });
});

let fsActiveCameraId = null;

export function openFullscreen(cameraId) {
    const cam = state.cameras.find(c => c.id === cameraId);
    if (!cam) return;

    fsActiveCameraId = cameraId;

    // CRITICAL FIX: Browsers limit 6 HTTP connections per host.
    // We already have 6 MJPEG streams running (grid). A 7th for fullscreen
    // gets BLOCKED FOREVER because MJPEG connections never close.
    // Solution: Kill all grid streams first, then open fullscreen.
    const allStreamImgs = document.querySelectorAll('#view-root img[src*="/stream/"]');
    allStreamImgs.forEach(img => {
        img.dataset.savedSrc = img.src;
        img.src = '';
    });

    // Update header
    document.getElementById('fs-cam-name').textContent = cam.name;
    document.getElementById('fs-cam-fps').textContent = 'LIVE';

    // Show overlay
    document.getElementById('fs-overlay').classList.add('active');

    // Now open fullscreen stream — browser has free connection slots
    document.getElementById('fs-video').src = `/stream/${cameraId}`;
}

export function closeFullscreen() {
    fsActiveCameraId = null;

    // Stop fullscreen stream
    document.getElementById('fs-video').src = '';

    // Hide overlay
    document.getElementById('fs-overlay').classList.remove('active');

    // Restore all grid streams
    const allStreamImgs = document.querySelectorAll('#view-root img[data-saved-src]');
    allStreamImgs.forEach(img => {
        img.src = img.dataset.savedSrc;
        delete img.dataset.savedSrc;
    });
}