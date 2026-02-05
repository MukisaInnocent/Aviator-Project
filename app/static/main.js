const API_BASE = '/api';

async function fetchAPI(endpoint, method = 'GET', body = null) {
    const headers = {
        'Content-Type': 'application/json'
    };

    // Simple check? Browsers handle cookies automatically for same-origin

    const options = {
        method,
        headers
    };

    if (body) {
        options.body = JSON.stringify(body);
    }

    try {
        const res = await fetch(`${API_BASE}${endpoint}`, options);

        let data;
        const contentType = res.headers.get("content-type");
        if (contentType && contentType.indexOf("application/json") !== -1) {
            data = await res.json();
        } else {
            // If not JSON, probably an error page
            const text = await res.text();
            throw new Error(`Server Error (${res.status}): ${text.substring(0, 100)}...`);
        }

        if (!res.ok) {
            if (res.status === 401) {
                // Redirect to login if not already there
                if (!window.location.pathname.includes('login.html') && !window.location.pathname.includes('register.html')) {
                    window.location.href = '/login';
                }
            }
            throw new Error(data.error || 'API Request Failed');
        }

        return data;
    } catch (err) {
        throw err;
    }
}

function showMessage(msg, type = 'error') {
    const el = document.getElementById('message-box');
    if (el) {
        el.textContent = msg;
        el.className = `alert ${type}`;
        el.style.display = 'block';
        setTimeout(() => el.style.display = 'none', 5000);
    } else {
        alert(msg);
    }
}

// Check auth on load for protected pages
async function checkAuth() {
    try {
        const user = await fetchAPI('/auth/me');
        // Update header user info if exists
        const balEl = document.getElementById('nav-balance');
        if (balEl) balEl.textContent = `$${user.balance.toFixed(2)}`;

        const userEl = document.getElementById('nav-user');
        if (userEl) userEl.textContent = user.username;

        return user;
    } catch (e) {
        // Not logged in
        return null;
    }
}
