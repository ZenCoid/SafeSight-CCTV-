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

    // Keyboard Shortcuts
    document.addEventListener('keydown', e => {
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

        // 1-6: Switch to that camera
        if (e.key >= '1' && e.key <= '6') {
            const idx = parseInt(e.key) - 1;
            if (state.cameras[idx]) {
                const btn = document.querySelector(`.cam-btn[data-cam="${state.cameras[idx].id}"]`);
                if (btn) btn.click();
            }
        }
        if (e.key.toLowerCase() === 'g') router.navigate('/');
        if (e.key.toLowerCase() === 's' && !e.ctrlKey && !e.metaKey) document.getElementById('sidebar').classList.toggle('collapsed');
    });
});