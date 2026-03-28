/**
 * Client authentication flow logic.
 * Handles login, registration, and session token storage.
 */

// If we are already logged in via a token, redirect to home immediately
// We only do this check on index.html and signup.html.
const currentPath = window.location.pathname;
if ((currentPath.endsWith('index.html') || currentPath.endsWith('signup.html') || currentPath === '/') && localStorage.getItem('crave_token')) {
    window.location.href = 'home.html';
}

function getApiBase() {
    return localStorage.getItem('CRAVE_API_BASE') || 'http://127.0.0.1:8000';
}

function displayError(msg) {
    const errorDiv = document.getElementById('auth-error');
    if (errorDiv) {
        errorDiv.textContent = msg;
        errorDiv.classList.remove('hidden');
    }
}

function clearError() {
    const errorDiv = document.getElementById('auth-error');
    if (errorDiv) {
        errorDiv.textContent = '';
        errorDiv.classList.add('hidden');
    }
}

async function handleAuthSubmission(event, endpoint) {
    event.preventDefault();
    clearError();

    const email = document.getElementById('email').value;
    const password = document.getElementById('password').value;

    const btn = event.target.querySelector('button[type="submit"]');
    const originalText = btn.textContent;
    btn.textContent = "Processing...";
    btn.disabled = true;

    try {
        const response = await fetch(`${getApiBase()}${endpoint}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ email, password })
        });

        if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            throw new Error(data.detail || 'Authentication failed');
        }

        const data = await response.json();
        if (data.access_token) {
            localStorage.setItem('crave_token', data.access_token);
            window.location.href = 'home.html';
        } else {
            throw new Error('No token received');
        }
    } catch (err) {
        displayError(err.message);
        btn.textContent = originalText;
        btn.disabled = false;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const loginForm = document.getElementById('login-form');
    if (loginForm) {
        loginForm.addEventListener('submit', (e) => handleAuthSubmission(e, '/api/auth/login'));
    }

    const signupForm = document.getElementById('signup-form');
    if (signupForm) {
        signupForm.addEventListener('submit', (e) => handleAuthSubmission(e, '/api/auth/register'));
    }
});
