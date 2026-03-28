/**
 * Hydrates extracted-recipe.html from GET /api/recipes/{session_id} (?session=).
 * Next: cooking-mode.html with the same session.
 */
(function () {
    "use strict";

    var base = (window.CRAVE_API_BASE || "http://127.0.0.1:8000").replace(/\/$/, "");
    var params = new URLSearchParams(window.location.search);
    var sessionId = params.get("session");

    var heroTitle = document.getElementById("extracted-hero-title");
    var heroMeta = document.getElementById("extracted-hero-meta");
    var heroImg = document.getElementById("extracted-hero-img");
    var dietaryBlurb = document.getElementById("extracted-dietary-blurb");
    var swapsEl = document.getElementById("extracted-swaps");
    var ingredientsEl = document.getElementById("extracted-ingredients-container");
    var altSection = document.getElementById("extracted-alternatives-section");
    var altBody = document.getElementById("extracted-alternatives-body");
    var startBtn = document.getElementById("extracted-start-cooking");
    var errEl = document.getElementById("extracted-error");

    function showError(msg) {
        if (errEl) {
            errEl.textContent = msg;
            errEl.classList.remove("hidden");
        }
        if (startBtn) startBtn.disabled = true;
    }

    function youtubeThumb(url) {
        if (!url) return null;
        var m =
            url.match(/[?&]v=([a-zA-Z0-9_-]{6,})/) ||
            url.match(/youtu\.be\/([a-zA-Z0-9_-]{6,})/) ||
            url.match(/\/shorts\/([a-zA-Z0-9_-]{6,})/);
        return m ? "https://img.youtube.com/vi/" + m[1] + "/hqdefault.jpg" : null;
    }

    function escapeHtml(s) {
        var d = document.createElement("div");
        d.textContent = s == null ? "" : String(s);
        return d.innerHTML;
    }

    if (!sessionId) {
        showError("Missing session. Start from Import.");
        return;
    }

    if (startBtn) {
        startBtn.addEventListener("click", function () {
            window.location.href =
                "cooking-mode.html?session=" + encodeURIComponent(sessionId);
        });
    }

    // ── Save button ────────────────────────────────────────────────
    var saveBtn = document.getElementById("save-recipe-btn");
    var saveIcon = document.getElementById("save-icon");
    var saveLabel = document.getElementById("save-label");

    if (saveBtn) {
        saveBtn.addEventListener("click", function () {
            if (saveBtn.dataset.saved) return; // already saved, ignore

            saveBtn.disabled = true;
            if (saveLabel) saveLabel.textContent = "Saving…";

            var token = localStorage.getItem("crave_token");
            fetch(base + "/api/saved", {
                method: "POST",
                headers: Object.assign(
                    { "Content-Type": "application/json" },
                    token ? { "Authorization": "Bearer " + token } : {}
                ),
                body: JSON.stringify({ session_id: sessionId })
            })
            .then(function (res) {
                if (res.status === 409) {
                    // Already saved — show saved state gracefully
                    return { already: true };
                }
                if (!res.ok) throw new Error("Could not save recipe");
                return res.json();
            })
            .then(function (data) {
                // Show saved state briefly, then redirect to Cookbook
                saveBtn.dataset.saved = "1";
                if (saveIcon) {
                    saveIcon.textContent = "bookmark";
                    saveIcon.style.fontVariationSettings = "'FILL' 1";
                }
                if (saveLabel) saveLabel.textContent = data && data.already ? "Saved" : "Saved!";
                setTimeout(function () {
                    window.location.href = "tracker.html";
                }, 600);
            })
            .catch(function (err) {
                saveBtn.disabled = false;
                if (saveLabel) saveLabel.textContent = "Save";
                alert(err.message);
            });
        });
    }

    fetch(base + "/api/recipes/" + encodeURIComponent(sessionId))
        .then(function (r) {
            return r.json().then(function (j) {
                if (!r.ok) {
                    throw new Error(j.detail || r.statusText || "Could not load recipe");
                }
                return j;
            });
        })
        .then(function (data) {
            var recipe = data.recipe || {};
            var name = recipe.recipe_name || "Recipe";
            var steps = recipe.steps || [];
            var ingredients = recipe.ingredients || [];

            if (heroTitle) heroTitle.textContent = name;
            if (heroMeta) {
                heroMeta.innerHTML =
                    '<span class="bg-white/20 backdrop-blur-md text-white text-xs font-bold px-3 py-1 rounded-full border border-white/20">' +
                    steps.length +
                    " step" +
                    (steps.length === 1 ? "" : "s") +
                    "</span>";
            }
            var thumb = youtubeThumb(recipe.source_url || "");
            if (heroImg && thumb) {
                heroImg.src = thumb;
                heroImg.alt = name;
            }

            if (dietaryBlurb) {
                dietaryBlurb.textContent =
                    recipe.dietary_summary ||
                    "Review ingredients below. Tap Start cooking when you are ready for step-by-step mode.";
            }

            if (swapsEl) {
                swapsEl.innerHTML = "";
                var conflicts = ingredients.filter(function (i) {
                    return i.dietary_conflict && (i.suggested_substitute || "").trim();
                });
                if (!conflicts.length) {
                    swapsEl.innerHTML =
                        '<p class="text-sm text-white/80">No automated swaps flagged for this recipe.</p>';
                } else {
                    conflicts.forEach(function (ing) {
                        var row = document.createElement("div");
                        row.className =
                            "flex flex-wrap items-center gap-2 sm:gap-3 bg-white/10 backdrop-blur-sm p-3 rounded-2xl border border-white/10";
                        row.innerHTML =
                            '<span class="material-symbols-outlined text-warning" style="font-variation-settings: \'FILL\' 1;">warning</span>' +
                            '<span class="text-xs font-medium line-through opacity-70">' +
                            escapeHtml(ing.item) +
                            "</span>" +
                            '<span class="material-symbols-outlined text-white text-[14px]">arrow_forward</span>' +
                            '<span class="text-sm font-bold text-[#b1f0ce]">' +
                            escapeHtml(ing.suggested_substitute) +
                            "</span>";
                        swapsEl.appendChild(row);
                    });
                }
            }

            if (ingredientsEl) {
                ingredientsEl.innerHTML = "";
                ingredients.forEach(function (ing) {
                    var label = document.createElement("label");
                    label.className = "flex items-center gap-4 cursor-pointer group";
                    var sub =
                        (ing.suggested_substitute || "").trim() && ing.dietary_conflict
                            ? '<span class="text-[10px] bg-primary-fixed/40 text-primary px-1.5 py-0.5 rounded-sm ml-1 no-underline">AI SWAP</span>'
                            : "";
                    label.innerHTML =
                        '<input type="checkbox" class="peer w-5 h-5 rounded-md border-outline-variant text-primary focus:ring-primary/40 focus:ring-offset-0 bg-transparent transition-all">' +
                        '<div class="flex-1 border-b border-outline-variant/10 pb-3 group-last:border-0 group-last:pb-0 peer-checked:opacity-60 peer-checked:line-through">' +
                        '<span class="font-medium text-[15px] group-hover:text-primary transition-colors">' +
                        escapeHtml(ing.item) +
                        sub +
                        "</span>" +
                        '<span class="block text-xs font-semibold text-on-surface-variant/70 uppercase tracking-wide">' +
                        escapeHtml(ing.amount || "") +
                        "</span></div>";
                    ingredientsEl.appendChild(label);
                });
            }

            var altCandidates = ingredients.filter(function (i) {
                return (
                    !(i.dietary_conflict && (i.suggested_substitute || "").trim()) &&
                    (i.suggested_substitute || "").trim()
                );
            });
            if (altSection && altBody) {
                if (!altCandidates.length) {
                    altSection.classList.add("hidden");
                } else {
                    altSection.classList.remove("hidden");
                    var first = altCandidates[0];
                    altBody.innerHTML =
                        "<p class=\"font-headline font-semibold text-sm mb-1\">Swap idea: " +
                        escapeHtml(first.item) +
                        "</p>" +
                        '<p class="text-xs text-on-surface-variant leading-relaxed">' +
                        escapeHtml(first.suggested_substitute) +
                        "</p>";
                }
            }
        })
        .catch(function (err) {
            showError(err.message || String(err));
        });
})();
