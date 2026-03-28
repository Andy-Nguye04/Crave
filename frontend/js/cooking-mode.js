/**
 * Cooking mode: recipe steps + Gemini Live Audio via CraveAudio engine.
 *
 * Expects window.CRAVE_API_BASE and query ?session=<uuid> from the import flow.
 * Requires crave-audio.js to be loaded first (provides window.CraveAudio).
 */
(function () {
    "use strict";

    var base = window.CRAVE_API_BASE || "http://127.0.0.1:8000";
    var params = new URLSearchParams(window.location.search);
    var sessionId = params.get("session");

    // DOM elements
    var titleEl = document.getElementById("crave-recipe-title");
    var stepLabelEl = document.getElementById("crave-step-label");
    var progressEl = document.getElementById("crave-progress");
    var instructionEl = document.getElementById("crave-instruction");
    var detailEl = document.getElementById("crave-detail");
    var ingredientsEl = document.getElementById("crave-ingredients-row");
    var chefStatusEl = document.getElementById("crave-chef-status");
    var wsStatusEl = document.getElementById("crave-ws-status");
    var timerBanner = document.getElementById("crave-timer-banner");

    var btnPrev = document.getElementById("crave-step-prev");
    var btnNext = document.getElementById("crave-step-next");
    var btnClose = document.getElementById("crave-close");
    var btnMute = document.getElementById("crave-mute-toggle");
    var startOverlay = document.getElementById("crave-start-overlay");
    var startBtn = document.getElementById("crave-start-btn");

    // State
    var recipe = null;
    var steps = [];
    var stepIdx = 0;
    var ws = null;
    var craveAudio = null;

    function wsUrl() {
        var u = base.replace(/^http/, "ws").replace(/\/$/, "");
        return u + "/ws/cooking/" + encodeURIComponent(sessionId);
    }

    function setChefStatus(t) {
        if (chefStatusEl) chefStatusEl.textContent = t;
    }

    function setWsStatus(t) {
        if (wsStatusEl) wsStatusEl.textContent = t;
    }

    // ---- Step rendering ----

    function renderStep() {
        if (!steps.length) return;
        var s = steps[stepIdx];
        var n = stepIdx + 1;
        if (stepLabelEl) stepLabelEl.textContent = "Step " + n + " of " + steps.length;
        if (progressEl) progressEl.style.width = Math.round((n / steps.length) * 100) + "%";
        if (instructionEl) instructionEl.textContent = s.instruction || "";
        if (detailEl) detailEl.textContent = s.visual_context || "";
        if (btnPrev) btnPrev.disabled = stepIdx <= 0;
        if (btnNext) {
            btnNext.disabled = steps.length === 0;
            btnNext.title = stepIdx >= steps.length - 1 ? "Finish recipe" : "Next step";
        }
    }

    function renderIngredients(list) {
        if (!ingredientsEl || !list || !list.length) return;
        ingredientsEl.innerHTML = "";
        list.forEach(function (ing) {
            var chip = document.createElement("div");
            chip.className =
                "flex-shrink-0 flex items-center gap-3 bg-surface-container-lowest py-2.5 px-4 rounded-full border border-outline-variant/20";
            chip.innerHTML =
                '<div class="flex flex-col"><span class="font-semibold text-sm">' +
                escapeHtml(ing.item) +
                '</span><span class="text-xs text-on-surface-variant">' +
                escapeHtml(ing.amount || "") +
                "</span></div>";
            ingredientsEl.appendChild(chip);
        });
    }

    function escapeHtml(s) {
        var d = document.createElement("div");
        d.textContent = s;
        return d.innerHTML;
    }

    // ---- WebSocket ----

    function notifyStepChanged() {
        if (!ws || ws.readyState !== WebSocket.OPEN) return;
        ws.send(JSON.stringify({
            type: "step_changed",
            step_number: stepIdx + 1,
        }));
    }

    function navigateToStep(stepNumber) {
        var idx = stepNumber - 1;
        if (idx < 0 || idx >= steps.length) return;
        stepIdx = idx;
        renderStep();
    }

    function connectWs() {
        if (!sessionId) return;
        try {
            ws = new WebSocket(wsUrl());
        } catch (e) {
            setWsStatus("WebSocket unavailable");
            return;
        }
        setWsStatus("Connecting…");
        ws.binaryType = "arraybuffer";

        ws.onopen = function () {
            setWsStatus("Connected");
            // Wire audio engine to the open socket
            if (craveAudio) {
                craveAudio.attachWs(ws);
                craveAudio.start();
            }
        };
        ws.onclose = function () {
            setWsStatus("Disconnected");
        };
        ws.onerror = function () {
            setWsStatus("Connection error");
        };
        ws.onmessage = function (ev) {
            // Binary frame = audio from Gemini
            if (ev.data instanceof ArrayBuffer) {
                if (craveAudio) craveAudio.playChunk(ev.data);
                return;
            }

            // Text frame = JSON control message
            try {
                var msg = JSON.parse(ev.data);
            } catch (e) {
                return;
            }

            if (msg.type === "live_ready") {
                setWsStatus("Crave is live");
                setChefStatus("Crave is warming up…");
            } else if (msg.type === "navigate_step" && msg.step_number) {
                navigateToStep(msg.step_number);
            } else if (msg.type === "kitchen_timer" && msg.duration_seconds) {
                showTimer(msg.duration_seconds);
            } else if (msg.type === "error" && msg.message) {
                setWsStatus(msg.message);
            }
        };
    }

    // ---- Timer ----

    function showTimer(seconds) {
        if (!timerBanner) {
            alert("Timer: " + seconds + " seconds");
            return;
        }
        var left = seconds;
        timerBanner.classList.remove("hidden");
        timerBanner.textContent = "Timer: " + left + "s";
        var id = setInterval(function () {
            left -= 1;
            if (left <= 0) {
                clearInterval(id);
                timerBanner.classList.add("hidden");
                return;
            }
            timerBanner.textContent = "Timer: " + left + "s";
        }, 1000);
    }

    // ---- Start flow (user gesture required for mic + audio) ----

    async function startCrave() {
        if (startOverlay) startOverlay.classList.add("hidden");

        try {
            craveAudio = new window.CraveAudio();
            // Show interim transcripts in the chef status bar
            craveAudio.onTranscript = function (text, isFinal) {
                if (isFinal) {
                    setChefStatus("You said: "" + text + """);
                } else {
                    setChefStatus("Hearing: " + text + "…");
                }
            };
            await craveAudio.init();
            setChefStatus("Mic ready — connecting to Crave…");
        } catch (err) {
            console.error("Mic error:", err);
            setChefStatus("Mic access denied");
        }

        connectWs();
    }

    // ---- Navigation event handlers ----

    if (btnPrev) {
        btnPrev.addEventListener("click", function () {
            if (stepIdx > 0) {
                stepIdx -= 1;
                renderStep();
                notifyStepChanged();
            }
        });
    }
    if (btnNext) {
        btnNext.addEventListener("click", function () {
            if (!steps.length) return;
            if (stepIdx < steps.length - 1) {
                stepIdx += 1;
                renderStep();
                notifyStepChanged();
            } else {
                // Last step — clean up and go to finish
                if (craveAudio) craveAudio.stop();
                if (ws) ws.close();
                window.location.href =
                    "cooking-mode-finish.html?session=" + encodeURIComponent(sessionId);
            }
        });
    }
    if (btnClose) {
        btnClose.addEventListener("click", function () {
            if (craveAudio) craveAudio.stop();
            if (ws) ws.close();
            window.location.href = "tracker.html";
        });
    }
    if (btnMute) {
        btnMute.addEventListener("click", function () {
            if (!craveAudio) return;
            var muted = craveAudio.toggleMute();
            var icon = btnMute.querySelector(".material-symbols-outlined");
            if (icon) icon.textContent = muted ? "mic_off" : "mic";
            setChefStatus(muted ? "Mic muted — Crave can still talk" : "Listening…");
        });
    }
    if (startBtn) {
        startBtn.addEventListener("click", startCrave);
    }

    // ---- Load recipe ----

    if (!sessionId) {
        setWsStatus("Missing ?session= — start from Import.");
        return;
    }

    fetch(
        base.replace(/\/$/, "") +
            "/api/recipes/" +
            encodeURIComponent(sessionId),
    )
        .then(function (r) {
            return r.json().then(function (j) {
                if (!r.ok) throw new Error(j.detail || r.statusText);
                return j;
            });
        })
        .then(function (data) {
            recipe = data.recipe;
            if (titleEl) titleEl.textContent = recipe.recipe_name || "Crave";
            steps = recipe.steps || [];
            steps.sort(function (a, b) {
                return (a.step_number || 0) - (b.step_number || 0);
            });
            renderIngredients(recipe.ingredients || []);
            stepIdx = 0;
            renderStep();
            // Don't auto-connect — wait for user to tap "Start Cooking with Crave"
        })
        .catch(function (err) {
            setWsStatus(err.message || String(err));
        });
})();
