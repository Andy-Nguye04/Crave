/**
 * Import flow: POST /api/parse-youtube → extracted-recipe → cooking mode → finish (?session=).
 *
 * Supports the simple form (`#import-form`, `#youtube-url`) and the styled import page
 * (`#recipeUrl`, `#extractBtn`, optional `#loadingOverlay`). Use dry-run to validate
 * without calling Gemini (no API key required for that path).
 */
(function () {
    "use strict";

    var form = document.getElementById("import-form");
    var urlInputSimple = document.getElementById("youtube-url");
    var dryRunEl = document.getElementById("dry-run");
    var statusEl = document.getElementById("import-status");
    var extractBtn = document.getElementById("extractBtn");
    var urlInputHero = document.getElementById("recipeUrl");
    var mainContent = document.getElementById("mainContent");
    var bottomNav = document.getElementById("bottomNav");
    var loadingOverlay = document.getElementById("loadingOverlay");
    var loadingTitle = document.getElementById("loadingTitle");
    var loadingSubtitle = document.getElementById("loadingSubtitle");

    var stageInterval = null;

    function apiOrigin() {
        return (window.CRAVE_API_BASE || "http://127.0.0.1:8000").replace(/\/$/, "");
    }

    function setStatus(msg, isError) {
        if (!statusEl) return;
        statusEl.textContent = msg;
        statusEl.className =
            "text-sm mt-3 text-center px-2 " +
            (isError ? "text-red-600 font-medium" : "text-primary font-medium");
    }

    function parseDetail(j, r) {
        var d = j && j.detail;
        if (Array.isArray(d)) {
            d = d
                .map(function (x) {
                    return x.msg || JSON.stringify(x);
                })
                .join("; ");
        }
        return d || r.statusText || "Parse failed";
    }

    function postParse(url, dryRun) {
        var headers = { "Content-Type": "application/json" };
        var token = localStorage.getItem("crave_token");
        if (token) {
            headers["Authorization"] = "Bearer " + token;
        }
        return fetch(apiOrigin() + "/api/parse-youtube", {
            method: "POST",
            headers: headers,
            body: JSON.stringify({
                youtube_url: url.trim(),
                dry_run: !!dryRun,
            }),
        }).then(function (r) {
            return r.json().then(function (j) {
                if (!r.ok) {
                    throw new Error(parseDetail(j, r));
                }
                return j;
            });
        });
    }

    function redirectAfterParse(sessionId) {
        window.location.href =
            "extracted-recipe.html?session=" + encodeURIComponent(sessionId);
    }

    function startStageMessages() {
        if (!loadingTitle || !loadingSubtitle) return;
        var stages = [
            { t: "Parsing video…", s: "Analyzing frames & captions" },
            { t: "Extracting ingredients…", s: "Building your shopping list" },
            { t: "Calibrating swaps…", s: "Dietary flags & substitutes" },
        ];
        var i = 0;
        loadingTitle.textContent = stages[0].t;
        loadingSubtitle.textContent = stages[0].s;
        stageInterval = window.setInterval(function () {
            i = Math.min(i + 1, stages.length - 1);
            loadingTitle.textContent = stages[i].t;
            loadingSubtitle.textContent = stages[i].s;
        }, 2200);
    }

    function stopStageMessages() {
        if (stageInterval !== null) {
            window.clearInterval(stageInterval);
            stageInterval = null;
        }
    }

    function showHeroLoader() {
        if (!mainContent || !loadingOverlay) return;
        if (bottomNav) bottomNav.style.display = "none";
        mainContent.classList.remove("opacity-100");
        mainContent.classList.add("opacity-0");
        window.setTimeout(function () {
            mainContent.style.display = "none";
            loadingOverlay.classList.remove("hidden");
            loadingOverlay.classList.add("flex");
            requestAnimationFrame(function () {
                loadingOverlay.classList.remove("opacity-0");
                loadingOverlay.classList.add("opacity-100");
            });
            startStageMessages();
        }, 300);
    }

    function hideHeroLoader() {
        stopStageMessages();
        if (!mainContent || !loadingOverlay) return;
        loadingOverlay.classList.remove("opacity-100");
        loadingOverlay.classList.add("opacity-0");
        window.setTimeout(function () {
            loadingOverlay.classList.add("hidden");
            loadingOverlay.classList.remove("flex");
            mainContent.style.display = "";
            mainContent.classList.remove("opacity-0");
            mainContent.classList.add("opacity-100");
            if (bottomNav) bottomNav.style.display = "";
        }, 300);
    }

    function isDryRun() {
        return !!(dryRunEl && dryRunEl.checked);
    }

    if (form && urlInputSimple) {
        form.addEventListener("submit", function (ev) {
            ev.preventDefault();
            var url = (urlInputSimple.value || "").trim();
            if (!url) {
                setStatus("Please paste a YouTube URL.", true);
                return;
            }
            setStatus("Parsing…", false);
            postParse(url, isDryRun())
                .then(function (data) {
                    redirectAfterParse(data.session_id);
                })
                .catch(function (err) {
                    setStatus(err.message || String(err), true);
                });
        });
    }

    if (extractBtn && urlInputHero) {
        extractBtn.addEventListener("click", function () {
            var url = (urlInputHero.value || "").trim();
            if (!url) {
                urlInputHero.focus();
                var wrap = urlInputHero.closest(".border-2");
                if (wrap) {
                    wrap.classList.add("border-red-500");
                    window.setTimeout(function () {
                        wrap.classList.remove("border-red-500");
                    }, 500);
                }
                setStatus("Please paste a YouTube URL.", true);
                return;
            }
            setStatus("", false);
            showHeroLoader();
            postParse(url, isDryRun())
                .then(function (data) {
                    stopStageMessages();
                    redirectAfterParse(data.session_id);
                })
                .catch(function (err) {
                    hideHeroLoader();
                    setStatus(err.message || String(err), true);
                });
        });
    }

    var pasteUrlBtn = document.getElementById("pasteUrlBtn");
    if (pasteUrlBtn && urlInputHero) {
        pasteUrlBtn.addEventListener("click", function () {
            if (navigator.clipboard && navigator.clipboard.readText) {
                navigator.clipboard
                    .readText()
                    .then(function (t) {
                        var s = (t || "").trim();
                        if (s) {
                            urlInputHero.value = s;
                        } else {
                            urlInputHero.focus();
                        }
                    })
                    .catch(function () {
                        urlInputHero.focus();
                    });
            } else {
                urlInputHero.focus();
            }
        });
    }
})();
