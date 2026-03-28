/**
 * Hydrates cooking-mode-finish.html from ?session= via GET /api/recipes/{session_id}.
 */
(function () {
    "use strict";

    var base = (window.CRAVE_API_BASE || "http://127.0.0.1:8000").replace(/\/$/, "");
    var params = new URLSearchParams(window.location.search);
    var sessionId = params.get("session");

    var stepSummaryEl = document.getElementById("finish-step-summary");
    var teaserEl = document.getElementById("finish-recipe-teaser");
    var platingEl = document.getElementById("finish-plating-text");
    var backCookingBtn = document.getElementById("finish-back-cooking");
    var logTrackerBtn = document.getElementById("log-tracker-btn");

    function cookingHref() {
        return sessionId
            ? "cooking-mode.html?session=" + encodeURIComponent(sessionId)
            : "cooking-mode.html";
    }

    if (backCookingBtn) {
        backCookingBtn.addEventListener("click", function () {
            window.location.href = cookingHref();
        });
    }

    if (!sessionId) {
        if (stepSummaryEl) stepSummaryEl.textContent = "Recipe complete";
        if (teaserEl) {
            teaserEl.textContent =
                "Open this page after cooking with a session link to see your recipe name here.";
        }
        return;
    }

    // Set up tags toggling
    var tags = [];
    document.querySelectorAll(".flex-wrap button").forEach(function(btn) {
        if (btn.textContent.includes("Add Note")) return;
        btn.addEventListener("click", function() {
            btn.classList.toggle("bg-primary");
            btn.classList.toggle("text-white");
            btn.classList.toggle("border-primary");
        });
    });

    if (logTrackerBtn) {
        logTrackerBtn.addEventListener("click", function () {
            var originalHtml = logTrackerBtn.innerHTML;
            logTrackerBtn.innerHTML = "Logging...";
            logTrackerBtn.disabled = true;

            var ratingInput = document.querySelector('input[name="rate"]:checked');
            var rating = ratingInput ? parseInt(ratingInput.value, 10) : 5; // Default to 5

            var activeTags = [];
            document.querySelectorAll(".flex-wrap button.bg-primary").forEach(function(b) {
                var text = b.textContent.trim();
                if (text && !text.includes("Add Note")) activeTags.push(text);
            });

            var token = localStorage.getItem("crave_token");
            fetch(base + "/api/history", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    ...(token ? { "Authorization": "Bearer " + token } : {})
                },
                body: JSON.stringify({
                    session_id: sessionId,
                    rating: rating,
                    tags: activeTags
                })
            }).then(function(res) {
                if (!res.ok) throw new Error("Failed to log history");
                window.location.href = "tracker.html";
            }).catch(function(err) {
                alert(err.message);
                logTrackerBtn.innerHTML = originalHtml;
                logTrackerBtn.disabled = false;
            });
        });
    }

    fetch(base + "/api/recipes/" + encodeURIComponent(sessionId))
        .then(function (r) {
            return r.json().then(function (j) {
                if (!r.ok) {
                    throw new Error(j.detail || r.statusText);
                }
                return j;
            });
        })
        .then(function (data) {
            var recipe = data.recipe || {};
            var steps = recipe.steps || [];
            steps.sort(function (a, b) {
                return (a.step_number || 0) - (b.step_number || 0);
            });
            var n = steps.length;
            if (stepSummaryEl) {
                stepSummaryEl.textContent =
                    n > 0 ? "Step " + n + " of " + n : "Recipe complete";
            }
            if (teaserEl) {
                teaserEl.textContent =
                    "You've successfully cooked " +
                    (recipe.recipe_name || "this recipe") +
                    ".";
            }
            if (platingEl) {
                var last = steps.length ? steps[steps.length - 1] : null;
                var hint =
                    (last && (last.visual_context || "").trim()) ||
                    (last && (last.instruction || "").trim()) ||
                    "";
                platingEl.textContent = hint
                    ? hint
                    : "Plate with care—taste for seasoning and add a fresh garnish if you like.";
            }
        })
        .catch(function () {
            if (teaserEl) {
                teaserEl.textContent =
                    "Great job finishing up! (Could not reload recipe details.)";
            }
        });
})();
