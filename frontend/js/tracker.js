/**
 * Hydrates tracker.html.
 * - "Cooked" tab: GET /api/history?sort_by=ranked  (ranked by rating)
 * - "Saved"  tab: GET /api/saved                   (newest first)
 */
(function () {
    "use strict";

    var base = (window.CRAVE_API_BASE || "http://127.0.0.1:8000").replace(/\/$/, "");
    var historyList = document.getElementById("tracker-history-list");
    var eyebrow = document.getElementById("tracker-eyebrow");
    var heading = document.getElementById("tracker-heading");
    var tabCooked = document.getElementById("tab-cooked");
    var tabSaved = document.getElementById("tab-saved");
    var currentTab = "cooked";

    function setActiveTab(tab) {
        if (tab === "cooked") {
            tabCooked.classList.add("bg-surface-container-lowest", "shadow-sm", "text-on-surface");
            tabCooked.classList.remove("text-on-surface-variant");
            tabSaved.classList.remove("bg-surface-container-lowest", "shadow-sm", "text-on-surface");
            tabSaved.classList.add("text-on-surface-variant");
            if (eyebrow) eyebrow.textContent = "Ranked Mastery";
            if (heading) heading.textContent = "Your Top Recipes";
        } else {
            tabSaved.classList.add("bg-surface-container-lowest", "shadow-sm", "text-on-surface");
            tabSaved.classList.remove("text-on-surface-variant");
            tabCooked.classList.remove("bg-surface-container-lowest", "shadow-sm", "text-on-surface");
            tabCooked.classList.add("text-on-surface-variant");
            if (eyebrow) eyebrow.textContent = "Bookmarked";
            if (heading) heading.textContent = "Saved Recipes";
        }
    }

    if (tabCooked) tabCooked.addEventListener("click", function () {
        if (currentTab === "cooked") return;
        currentTab = "cooked";
        setActiveTab("cooked");
        loadCooked();
    });

    if (tabSaved) tabSaved.addEventListener("click", function () {
        if (currentTab === "saved") return;
        currentTab = "saved";
        setActiveTab("saved");
        loadSaved();
    });

    function authHeaders() {
        var token = localStorage.getItem("crave_token");
        return token ? { "Authorization": "Bearer " + token } : {};
    }

    function showLoading() {
        if (historyList) historyList.innerHTML = '<div class="text-center py-10"><p class="text-on-surface-variant text-sm font-medium">Loading...</p></div>';
    }

    function showError(msg) {
        if (historyList) historyList.innerHTML =
            '<div class="text-center py-10">' +
            '<span class="material-symbols-outlined text-4xl text-outline-variant mb-2">error</span>' +
            '<p class="text-on-surface-variant font-medium text-sm">' + escapeHtml(msg) + '</p>' +
            '<a href="index.html" class="inline-block mt-4 px-4 py-2 bg-primary text-white text-xs font-bold rounded-full">Sign In</a>' +
            '</div>';
    }

    function escapeHtml(s) {
        var d = document.createElement("div");
        d.textContent = String(s || "");
        return d.innerHTML;
    }

    // ── Cooked tab ──────────────────────────────────────────────────
    function loadCooked() {
        showLoading();
        fetch(base + "/api/history?sort_by=ranked", { headers: authHeaders() })
            .then(function (res) {
                if (!res.ok) throw new Error("Sign in to view your Cookbook");
                return res.json();
            })
            .then(renderCooked)
            .catch(function (err) { showError(err.message); });
    }

    function renderCooked(items) {
        if (!historyList) return;
        historyList.innerHTML = "";

        if (!items.length) {
            historyList.innerHTML =
                '<div class="text-center py-12 bg-surface-container-lowest border border-outline-variant/10 rounded-2xl">' +
                '<span class="material-symbols-outlined text-5xl text-outline-variant mb-2">restaurant_menu</span>' +
                '<h4 class="font-headline font-bold text-lg mb-1">Cookbook is empty</h4>' +
                '<p class="text-sm text-on-surface-variant px-6">You haven\'t logged any recipes yet. Import a cooking video to get started!</p>' +
                '</div>';
            return;
        }

        items.forEach(function (item, idx) {
            var rank = idx + 1;
            var thumb = item.thumbnail_url || "https://images.unsplash.com/photo-1546069901-ba9599a7e63c?w=400&h=400&fit=crop";
            var displayTag = item.tags && item.tags.length ? item.tags[0] : "AI Supported";
            var tagIcon = item.rating >= 4 ? "thumb_up" : "psychology";
            var rankColor = rank === 1 ? "text-primary" : "text-on-surface-variant";
            var borderClass = rank === 1 ? "border border-primary/20" : "border border-outline-variant/10";

            var card = document.createElement("div");
            card.className = "group relative flex rounded-2xl overflow-hidden hover:shadow-xl transition-all cursor-pointer p-4 gap-4 items-center bg-surface-container-lowest " + borderClass;
            card.innerHTML =
                '<div class="w-10 flex flex-col items-center justify-center font-headline">' +
                '<span class="text-xl font-black ' + rankColor + '">#' + rank + '</span>' +
                '<span class="text-[10px] text-on-surface-variant font-bold mt-1 text-center">' + item.rating + ' <span class="material-symbols-outlined text-[10px]" style="font-variation-settings: \'FILL\' 1;">star</span></span>' +
                '</div>' +
                '<div class="w-20 h-20 rounded-xl overflow-hidden flex-shrink-0 bg-surface-container">' +
                '<img src="' + escapeHtml(thumb) + '" alt="Thumbnail" class="w-full h-full object-cover group-hover:scale-110 transition-transform duration-500" />' +
                '</div>' +
                '<div class="flex-grow">' +
                '<h4 class="font-headline font-bold text-lg leading-tight mb-1">' + escapeHtml(item.recipe_name) + '</h4>' +
                '<p class="text-xs text-on-surface-variant font-medium flex gap-2 items-center">' +
                '<span class="material-symbols-outlined text-[14px]">' + tagIcon + '</span> ' + escapeHtml(displayTag) +
                '</p>' +
                '</div>';

            if (item.session_id) {
                card.addEventListener("click", function () {
                    window.location.href = "extracted-recipe.html?session=" + encodeURIComponent(item.session_id) + "&from=tracker";
                });
            } else if (item.source_url) {
                card.addEventListener("click", function () { window.open(item.source_url, "_blank"); });
            }
            historyList.appendChild(card);
        });
    }

    // ── Saved tab ────────────────────────────────────────────────────
    function loadSaved() {
        showLoading();
        fetch(base + "/api/saved", { headers: authHeaders() })
            .then(function (res) {
                if (!res.ok) throw new Error("Sign in to view your saved recipes");
                return res.json();
            })
            .then(renderSaved)
            .catch(function (err) { showError(err.message); });
    }

    function renderSaved(items) {
        if (!historyList) return;
        historyList.innerHTML = "";

        if (!items.length) {
            historyList.innerHTML =
                '<div class="text-center py-12 bg-surface-container-lowest border border-outline-variant/10 rounded-2xl">' +
                '<span class="material-symbols-outlined text-5xl text-outline-variant mb-2">bookmark</span>' +
                '<h4 class="font-headline font-bold text-lg mb-1">No saved recipes</h4>' +
                '<p class="text-sm text-on-surface-variant px-6">Tap Save on any extracted recipe to bookmark it here for later.</p>' +
                '</div>';
            return;
        }

        items.forEach(function (item) {
            var thumb = item.thumbnail_url || "https://images.unsplash.com/photo-1546069901-ba9599a7e63c?w=400&h=400&fit=crop";

            var card = document.createElement("div");
            card.className = "group relative flex rounded-2xl overflow-hidden hover:shadow-xl transition-all cursor-pointer p-4 gap-4 items-center bg-surface-container-lowest border border-outline-variant/10";
            card.innerHTML =
                '<div class="w-10 flex flex-col items-center justify-center">' +
                '<span class="material-symbols-outlined text-primary" style="font-variation-settings: \'FILL\' 1;">bookmark</span>' +
                '</div>' +
                '<div class="w-20 h-20 rounded-xl overflow-hidden flex-shrink-0 bg-surface-container">' +
                '<img src="' + escapeHtml(thumb) + '" alt="Thumbnail" class="w-full h-full object-cover group-hover:scale-110 transition-transform duration-500" />' +
                '</div>' +
                '<div class="flex-grow">' +
                '<h4 class="font-headline font-bold text-lg leading-tight mb-1">' + escapeHtml(item.recipe_name) + '</h4>' +
                '<p class="text-xs text-on-surface-variant font-medium flex gap-2 items-center">' +
                '<span class="material-symbols-outlined text-[14px]">open_in_new</span> ' + (item.session_id ? 'See recipe' : 'Tap to watch original') +
                '</p>' +
                '</div>';

            if (item.session_id) {
                card.addEventListener("click", function () {
                    window.location.href = "extracted-recipe.html?session=" + encodeURIComponent(item.session_id) + "&from=tracker";
                });
            } else if (item.source_url) {
                card.addEventListener("click", function () { window.open(item.source_url, "_blank"); });
            }
            historyList.appendChild(card);
        });
    }

    // Boot with Cooked tab
    setActiveTab("cooked");
    loadCooked();

})();
