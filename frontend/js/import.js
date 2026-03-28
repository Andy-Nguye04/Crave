/**
 * Import flow: paste YouTube URL → POST /api/parse-youtube → redirect to cooking mode.
 *
 * Use dry-run to validate UI without calling Gemini (no API key required for that path).
 */
(function () {
    "use strict";

    var form = document.getElementById("import-form");
    var urlInput = document.getElementById("youtube-url");
    var dryRun = document.getElementById("dry-run");
    var statusEl = document.getElementById("import-status");
    var base = window.CRAVE_API_BASE || "http://127.0.0.1:8000";

    function setStatus(msg, isError) {
        if (!statusEl) return;
        statusEl.textContent = msg;
        statusEl.className =
            "text-sm mt-2 " + (isError ? "text-error font-medium" : "text-secondary");
    }

    if (form) {
        form.addEventListener("submit", function (ev) {
            ev.preventDefault();
            var url = (urlInput && urlInput.value) || "";
            if (!url.trim()) {
                setStatus("Please paste a YouTube URL.", true);
                return;
            }
            setStatus("Parsing…", false);
            fetch(base.replace(/\/$/, "") + "/api/parse-youtube", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    youtube_url: url.trim(),
                    dry_run: !!(dryRun && dryRun.checked),
                }),
            })
                .then(function (r) {
                    return r.json().then(function (j) {
                        if (!r.ok) {
                            var d = j && j.detail;
                            if (Array.isArray(d)) {
                                d = d.map(function (x) {
                                    return x.msg || JSON.stringify(x);
                                }).join("; ");
                            }
                            throw new Error(d || r.statusText || "Parse failed");
                        }
                        return j;
                    });
                })
                .then(function (data) {
                    window.location.href =
                        "cooking-mode.html?session=" +
                        encodeURIComponent(data.session_id);
                })
                .catch(function (err) {
                    setStatus(err.message || String(err), true);
                });
        });
    }
})();
