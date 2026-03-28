/**
 * Central place for the browser to find the Crave API origin.
 *
 * Set before other scripts load:
 *   localStorage.setItem('CRAVE_API_BASE', 'http://127.0.0.1:8000')
 * Or pass ?api=http://127.0.0.1:8000 on import or cooking-mode pages.
 */
(function () {
    "use strict";
    var params = new URLSearchParams(window.location.search);
    var fromQuery = params.get("api");
    if (fromQuery) {
        try {
            localStorage.setItem("CRAVE_API_BASE", fromQuery);
        } catch (e) { /* ignore */ }
    }
    window.CRAVE_API_BASE =
        (typeof localStorage !== "undefined" &&
            localStorage.getItem("CRAVE_API_BASE")) ||
        "http://127.0.0.1:8000";
})();
