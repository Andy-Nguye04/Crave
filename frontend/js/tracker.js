/**
 * Hydrates tracker.html from GET /api/history
 */
(function () {
    "use strict";

    var base = (window.CRAVE_API_BASE || "http://127.0.0.1:8000").replace(/\/$/, "");
    var historyList = document.getElementById("tracker-history-list");
    var currentSort = "ranked";

    // Wire up Ranked / Recent toggle buttons
    var sortButtons = document.querySelectorAll(".bg-surface-container-low button");
    sortButtons.forEach(function(btn) {
        btn.addEventListener("click", function() {
            var sortMode = btn.textContent.trim().toLowerCase();
            if (sortMode === currentSort) return;
            currentSort = sortMode;

            // Update active styles
            sortButtons.forEach(function(b) {
                b.classList.remove("bg-surface-container-lowest", "shadow-sm", "text-on-surface");
                b.classList.add("text-on-surface-variant");
            });
            btn.classList.add("bg-surface-container-lowest", "shadow-sm", "text-on-surface");
            btn.classList.remove("text-on-surface-variant");

            loadHistory(currentSort);
        });
    });

    function loadHistory(sortBy) {
        sortBy = sortBy || "ranked";
        var token = localStorage.getItem("crave_token");
        var headers = {};
        if (token) headers["Authorization"] = "Bearer " + token;

        // Show loading state
        if (historyList) {
            historyList.innerHTML = '<div class="text-center py-10"><p class="text-on-surface-variant text-sm font-medium">Loading...</p></div>';
        }

        fetch(base + "/api/history?sort_by=" + sortBy, { headers: headers })
            .then(function(res) {
                if (!res.ok) throw new Error("Ensure you are logged in");
                return res.json();
            })
            .then(function(data) {
                renderHistory(data);
            })
            .catch(function(err) {
                if (historyList) {
                    historyList.innerHTML = '\
                        <div class="text-center py-10">\
                            <span class="material-symbols-outlined text-4xl text-warning mb-2">error</span>\
                            <p class="text-on-surface-variant font-medium text-sm">' + err.message + '</p>\
                            <a href="index.html" class="inline-block mt-4 px-4 py-2 bg-primary text-white text-xs font-bold rounded-full">Sign In</a>\
                        </div>';
                }
            });
    }

    function escapeHtml(s) {
        var d = document.createElement("div");
        d.textContent = s;
        return d.innerHTML;
    }

    function renderHistory(items) {
        if (!historyList) return;
        historyList.innerHTML = "";

        if (items.length === 0) {
            historyList.innerHTML = '\
                <div class="text-center py-12 bg-surface-container-lowest border border-outline-variant/10 rounded-2xl">\
                     <span class="material-symbols-outlined text-5xl text-outline-variant mb-2">restaurant_menu</span>\
                     <h4 class="font-headline font-bold text-lg mb-1">Cookbook is empty</h4>\
                     <p class="text-sm text-on-surface-variant px-6">You haven\'t logged any recipes yet. Import a cooking video to get started!</p>\
                </div>';
            return;
        }

        items.forEach(function(item, idx) {
            var rank = idx + 1;
            // Provide a generic fallback image if we fail to scrape YouTube
            var thumb = item.thumbnail_url || "https://images.unsplash.com/photo-1546069901-ba9599a7e63c?w=400&h=400&fit=crop";

            var tagsHtml = "";
            var displayTag = item.tags.length > 0 ? item.tags[0] : "AI Supported";
            var tagIcon = item.rating >= 4 ? "thumb_up" : "psychology";

            var bgClass = rank === 1 ? "bg-surface-container-lowest border border-primary/20" : "bg-surface-container-lowest border border-outline-variant/10";
            var rankColor = rank === 1 ? "text-primary" : "text-on-surface-variant";

            var card = document.createElement("div");
            card.className = "group relative flex rounded-2xl overflow-hidden hover:shadow-xl transition-all cursor-pointer p-4 gap-4 items-center " + bgClass;
            
            card.innerHTML = '\
                <div class="w-10 flex flex-col items-center justify-center font-headline">\
                    <span class="text-xl font-black ' + rankColor + '">#' + rank + '</span>\
                    <span class="text-[10px] text-on-surface-variant font-bold mt-1 text-center">' + item.rating + ' <span class="material-symbols-outlined text-[10px]" style="font-variation-settings: \'FILL\' 1;">star</span></span>\
                </div>\
                <div class="w-20 h-20 rounded-xl overflow-hidden flex-shrink-0 bg-surface-container">\
                    <img src="' + escapeHtml(thumb) + '" alt="Thumbnail" class="w-full h-full object-cover group-hover:scale-110 transition-transform duration-500" />\
                </div>\
                <div class="flex-grow">\
                    <h4 class="font-headline font-bold text-lg leading-tight mb-1">' + escapeHtml(item.recipe_name) + '</h4>\
                    <p class="text-xs text-on-surface-variant font-medium flex gap-2 items-center">\
                        <span class="material-symbols-outlined text-[14px]">' + tagIcon + '</span> ' + escapeHtml(displayTag) + '\
                    </p>\
                </div>\
            ';

            // Optional: link it to the source or recipe overview
            card.addEventListener('click', function() {
                if (item.source_url) {
                    window.open(item.source_url, '_blank');
                }
            });

            historyList.appendChild(card);
        });
    }

    loadHistory();

})();
