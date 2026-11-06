const API_BASE = '/api';

// Escape any value before interpolating it into an HTML string.
function escapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

// Jet silhouette in a 100x40 box, nose pointing right (same shape as the SVG in base.html).
const JET_BODY_PATH = 'M4 20C4 16 10 15 20 15L72 15C84 15 94 17 98 20C94 23 84 25 72 25L20 25C10 25 4 24 4 20Z M46 18L34 3L42 3L64 17Z M44 22L30 38L39 38L64 23Z M9 17L3 4L10 4L22 16Z M10 23L4 31L11 31L23 24Z';
const JET_WINDOW_PATH = 'M78 17.2C84 17.2 90 18 93.5 19.6L79 19.6Z';

const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

async function fetchAPI(endpoint, method = 'GET', body = null) {
    const options = {
        method,
        headers: { 'Content-Type': 'application/json' },
    };
    if (body) {
        options.body = JSON.stringify(body);
    }

    const res = await fetch(`${API_BASE}${endpoint}`, options);

    let data;
    const contentType = res.headers.get('content-type');
    if (contentType && contentType.includes('application/json')) {
        data = await res.json();
    } else {
        const text = await res.text();
        throw new Error(`Server Error (${res.status}): ${text.substring(0, 100)}...`);
    }

    if (!res.ok) {
        if (res.status === 401) {
            const path = window.location.pathname;
            if (!path.startsWith('/login') && !path.startsWith('/register')) {
                window.location.href = '/login';
            }
        }
        throw new Error(data.error || 'API Request Failed');
    }

    return data;
}

let toastTimer = null;
function showMessage(msg, type = 'error') {
    const el = document.getElementById('message-box');
    if (!el) {
        alert(msg);
        return;
    }
    el.textContent = msg;
    el.className = `alert ${type}`;
    void el.offsetWidth; // restart the entrance animation
    el.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove('show'), 4200);
}

function formatCredits(value) {
    return Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// Smoothly count an element's number from its current value to `target`.
function animateNumber(el, target, { suffix = '', duration = 700 } = {}) {
    if (!el) return;
    const from = Number(el.dataset.value ?? target);
    el.dataset.value = target;
    if (prefersReducedMotion || from === target) {
        el.textContent = `${formatCredits(target)}${suffix}`;
        return;
    }
    el.classList.remove('bump-up', 'bump-down');
    void el.offsetWidth;
    el.classList.add(target > from ? 'bump-up' : 'bump-down');
    const start = performance.now();
    const step = (now) => {
        const t = Math.min(1, (now - start) / duration);
        const eased = 1 - Math.pow(1 - t, 3);
        el.textContent = `${formatCredits(from + (target - from) * eased)}${suffix}`;
        if (t < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
}

// Check auth on load for protected pages and refresh the header.
async function checkAuth() {
    try {
        const user = await fetchAPI('/auth/me');
        animateNumber(document.getElementById('nav-balance'), user.balance, { suffix: ' cr' });

        const userEl = document.getElementById('nav-user');
        if (userEl) userEl.textContent = user.username;
        const avatarEl = document.getElementById('nav-avatar');
        if (avatarEl) avatarEl.textContent = user.username.charAt(0).toUpperCase();

        return user;
    } catch (e) {
        return null;
    }
}

function relativeTime(iso) {
    const then = Date.parse(iso.endsWith('Z') ? iso : `${iso}Z`);
    if (Number.isNaN(then)) return iso;
    const secs = Math.round((Date.now() - then) / 1000);
    if (secs < 60) return 'just now';
    if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
    if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`;
    return new Date(then).toLocaleDateString();
}
