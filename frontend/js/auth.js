/**
 * Client authentication flow logic.
 * Demo mode: auto-login with a fixed demo token for hackathon judging.
 */

const DEMO_TOKEN = "crave-demo-token-hackathon";

// Always force the demo token so stale tokens never block access
localStorage.setItem('crave_token', DEMO_TOKEN);

// Always redirect to home from login/signup pages
const currentPath = window.location.pathname;
if (currentPath.endsWith('index.html') || currentPath.endsWith('signup.html') || currentPath === '/') {
    window.location.href = 'home.html';
}

function getApiBase() {
    return localStorage.getItem('CRAVE_API_BASE') || 'http://127.0.0.1:8000';
}
