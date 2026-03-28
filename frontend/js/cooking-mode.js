/**
 * Cooking mode: load recipe by session id, step navigation, Gemini Live WebSocket (TEXT).
 *
 * Expects window.CRAVE_API_BASE and query ?session=<uuid> from the import flow.
 */
(function () {
    "use strict";

    var base = window.CRAVE_API_BASE || "http://127.0.0.1:8000";
    var params = new URLSearchParams(window.location.search);
    var sessionId = params.get("session");

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
    var btnFast = document.getElementById("crave-fast-forward");
    var promptBar = document.getElementById("crave-prompt-bar");

    var recipe = null;
    var steps = [];
    var stepIdx = 0;
    var ws = null;

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

    function renderStep() {
        if (!steps.length) return;
        var s = steps[stepIdx];
        var n = stepIdx + 1;
        if (stepLabelEl) {
            stepLabelEl.textContent = "Step " + n + " of " + steps.length;
        }
        if (progressEl) {
            progressEl.style.width = Math.round((n / steps.length) * 100) + "%";
        }
        if (instructionEl) instructionEl.textContent = s.instruction || "";
        if (detailEl) {
            detailEl.textContent = s.visual_context || "";
        }
        if (btnPrev) btnPrev.disabled = stepIdx <= 0;
        /* Last step: next control finishes to cooking-mode-finish.html */
        if (btnNext) {
            btnNext.disabled = steps.length === 0;
            btnNext.title =
                steps.length && stepIdx >= steps.length - 1
                    ? "Finish recipe"
                    : "Next step";
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
                "<div class=\"flex flex-col\"><span class=\"font-semibold text-sm\">" +
                escapeHtml(ing.item) +
                "</span><span class=\"text-xs text-on-surface-variant\">" +
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

    function connectWs() {
        if (!sessionId) return;
        try {
            ws = new WebSocket(wsUrl());
        } catch (e) {
            setWsStatus("WebSocket unavailable");
            return;
        }
        setWsStatus("Connecting…");
        ws.onopen = function () {
            setWsStatus("Live ready");
        };
        ws.onclose = function () {
            setWsStatus("Disconnected");
        };
        ws.onerror = function () {
            setWsStatus("Error");
        };
        ws.onmessage = function (ev) {
            try {
                var msg = JSON.parse(ev.data);
            } catch (e) {
                return;
            }
            if (msg.type === "live_ready") {
                setWsStatus("Chef online");
            } else if (msg.type === "model_text" && msg.text) {
                setChefStatus(msg.text);
            } else if (msg.type === "transcription" && msg.text) {
                setChefStatus(
                    (msg.role === "user" ? "You: " : "Chef: ") + msg.text,
                );
            } else if (msg.type === "kitchen_timer" && msg.duration_seconds) {
                showTimer(msg.duration_seconds);
            } else if (msg.type === "error" && msg.message) {
                setWsStatus(msg.message);
            }
        };
    }

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

    function sendUserText(text) {
        if (!ws || ws.readyState !== WebSocket.OPEN) {
            setWsStatus("Connect the API (see README) to chat with the chef.");
            return;
        }
        ws.send(JSON.stringify({ type: "user_text", text: text }));
    }

    if (btnPrev) {
        btnPrev.addEventListener("click", function () {
            if (stepIdx > 0) {
                stepIdx -= 1;
                renderStep();
            }
        });
    }
    if (btnNext) {
        btnNext.addEventListener("click", function () {
            if (!steps.length) return;
            if (stepIdx < steps.length - 1) {
                stepIdx += 1;
                renderStep();
            } else {
                window.location.href =
                    "cooking-mode-finish.html?session=" +
                    encodeURIComponent(sessionId);
            }
        });
    }
    if (btnClose) {
        btnClose.addEventListener("click", function () {
            window.location.href = "tracker.html";
        });
    }
    if (btnFast) {
        btnFast.addEventListener("click", function () {
            sendUserText(
                "Please briefly recap the current step and ask if I am ready to continue.",
            );
        });
    }
    if (promptBar) {
        promptBar.addEventListener("click", function (ev) {
            var btn = ev.target.closest("button[data-prompt]");
            if (!btn) return;
            var t = btn.getAttribute("data-prompt");
            if (t) sendUserText(t);
        });
    }

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
                if (!r.ok) {
                    throw new Error(j.detail || r.statusText);
                }
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
            connectWs();
        })
        .catch(function (err) {
            setWsStatus(err.message || String(err));
        });
})();
