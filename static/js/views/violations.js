import { fetchViolations, state, formatTime } from '../api.js';

export default function render(container) {
    container.innerHTML = `
        <div class="glass-panel" style="padding: 24px; min-height: 500px;">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:24px;">
                <h2 class="text-h2">Recent Violations</h2>
                <button class="btn btn-primary" id="btn-refresh-log">Refresh Log</button>
            </div>
            
            <table class="table-container">
                <thead>
                    <tr>
                        <th>Time</th>
                        <th>Camera</th>
                        <th>Type</th>
                        <th>Confidence</th>
                        <th>Action</th>
                    </tr>
                </thead>
                <tbody id="violations-tbody">
                    <tr><td colspan="5" style="text-align:center;color:var(--text-muted)">Loading...</td></tr>
                </tbody>
            </table>
        </div>
    `;

    const tbody = document.getElementById('violations-tbody');

    const redraw = () => {
        if (!state.violations || state.violations.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--text-muted)">No violations recorded recently.</td></tr>';
            return;
        }

        tbody.innerHTML = state.violations.map(v => {
            const isVi = v.detection_type === 'no_helmet';
            const badgeBg = isVi ? 'var(--color-red-glow)' : 'var(--color-green-glow)';
            const badgeColor = isVi ? 'var(--color-red)' : 'var(--color-green)';
            const confPercent = Math.round(v.confidence * 100);

            return `
                <tr>
                    <td>${formatTime(v.timestamp)}</td>
                    <td style="font-weight:500">${v.camera_name || v.camera_id}</td>
                    <td>
                        <span style="background:${badgeBg};color:${badgeColor};padding:4px 8px;border-radius:4px;font-size:11px;font-weight:600;text-transform:uppercase;">
                            ${v.detection_type}
                        </span>
                    </td>
                    <td>
                        <div style="display:flex;align-items:center;gap:8px;">
                            ${confPercent}%
                            <div style="width:40px;height:4px;background:var(--bg-border);border-radius:2px;overflow:hidden">
                                <div style="width:${confPercent}%;height:100%;background:${isVi ? 'var(--color-red)': 'var(--color-teal)'}"></div>
                            </div>
                        </div>
                    </td>
                    <td>
                        ${v.snapshot_url 
                            ? `<a href="${v.snapshot_url}" target="_blank" class="btn style="padding:4px 8px">View Image</a>` 
                            : `<span class="text-small">No image</span>`}
                    </td>
                </tr>
            `;
        }).join('');
    };

    document.getElementById('btn-refresh-log').onclick = () => {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--text-muted)">Refreshing...</td></tr>';
        fetchViolations().then(redraw);
    };

    // initial fetch
    fetchViolations().then(redraw);

    // we don't need a heavy subscriber here, just redraw on mount
    return () => {}; 
}
