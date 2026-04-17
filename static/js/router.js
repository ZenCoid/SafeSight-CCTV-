import dashboardView from './views/dashboard.js';
import violationsView from './views/violations.js';
import camerasView from './views/cameras.js';
import settingsView from './views/settings.js';

const routes = {
    '/': { title: 'Dashboard', view: dashboardView },
    '/violations': { title: 'Violations', view: violationsView },
    '/cameras-page': { title: 'Cameras', view: camerasView },
    '/settings': { title: 'Settings', view: settingsView },
};

export class Router {
    constructor() {
        this.container = document.getElementById('view-root');
        this.currentCleanup = null;

        // Intercept link clicks
        document.addEventListener('click', (e) => {
            const link = e.target.closest('a[data-route]');
            if (link) {
                e.preventDefault();
                this.navigate(link.getAttribute('data-route') || link.getAttribute('href'));
            }
        });

        // Handle browser back/forward
        window.addEventListener('popstate', () => this.handleRoute());
    }

    navigate(path) {
        history.pushState(null, '', path);
        this.handleRoute();
    }

    handleRoute() {
        const path = window.location.pathname;
        const route = routes[path] || routes['/'];

        // Cleanup previous view
        if (this.currentCleanup) {
            this.currentCleanup();
            this.currentCleanup = null;
        }

        // Update page title
        document.getElementById('page-title').textContent = route.title;
        document.title = `SafeSight AI - ${route.title}`;

        // Update active nav item
        document.querySelectorAll('.nav-item').forEach(item => {
            const routePath = item.getAttribute('data-route');
            item.classList.toggle('active', routePath === path);
        });

        // Render view
        this.container.innerHTML = '';
        this.currentCleanup = route.view(this.container);
    }
}