/**
 * Cooking mode: recipe steps, Gemini Live WebSocket (native audio + transcription),
 * PCM playback in the browser, and Web Speech API for voice input.
 * After Live connects, the mic stays on: nothing is sent to the chef while a reply is in
 * progress (from your prompt until the stream goes quiet plus a short pause). Quick prompts
 * use the same gate. A failsafe timeout unlocks if the server sends no model activity.
 * Mic tap = one focused utterance (briefly stops continuous capture).
 *
 * Echo note: speakers + mic will transcribe the chef’s TTS as “user” speech. We stop
 * SpeechRecognition entirely while the chef is replying (network + PCM tail), then
 * restart only when the gate opens—on top of not sending until playback ends. Headphones
 * still help if echo leaks through.
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
    var audioCtx = null;
    var nextAudioTime = 0;
    /** Count of chef PCM BufferSources currently playing or scheduled (onended decrements). */
    var chefPcmSourcesPlaying = 0;
    /** performance.now() until which we stay muted after the last PCM buffer ends. */
    var chefPcmTailUntil = 0;
    /** Ms after last audible sample for room reverb / late ASR (not wall-clock guess). */
    var CHEF_PCM_TAIL_MS = 480;
    var wsLiveReconnects = 0;
    var wsGeneration = 0;

    // #region agent log
    var _agentLogVoiceThrottle = 0;
    function agentLogVoiceGate(reason, data) {
        var t = Date.now();
        if (t - _agentLogVoiceThrottle < 2200) return;
        _agentLogVoiceThrottle = t;
        fetch("http://127.0.0.1:7455/ingest/2d31700a-ba7f-4f1f-b7d2-843320053958", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-Debug-Session-Id": "36a370",
            },
            body: JSON.stringify({
                sessionId: "36a370",
                location: "cooking-mode.js:voice-gate",
                message: reason,
                data: data || {},
                timestamp: t,
                hypothesisId: "H-gate",
            }),
        }).catch(function () {});
    }
    // #endregion

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

    function ensureAudioContext() {
        if (!audioCtx) {
            audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        }
        if (audioCtx.state === "suspended") {
            return audioCtx.resume();
        }
        return Promise.resolve();
    }

    /** True while any chef PCM is still playing or within post-playback tail (echo guard). */
    function isChefTtsAudioPlaying() {
        if (chefPcmSourcesPlaying > 0) return true;
        if (!chefPcmTailUntil) return false;
        return performance.now() < chefPcmTailUntil;
    }

    function resetChefPcmPlaybackTracking() {
        chefPcmSourcesPlaying = 0;
        chefPcmTailUntil = 0;
        nextAudioTime = 0;
    }

    function parsePcmSampleRate(mimeType) {
        var rate = 24000;
        if (!mimeType) return rate;
        var m = /rate[=:](\d+)/i.exec(mimeType);
        if (m) {
            var n = parseInt(m[1], 10);
            if (n > 0) rate = n;
        }
        return rate;
    }

    function mimeLooksLikeRawPcm(mimeType) {
        var m = (mimeType || "").toLowerCase();
        if (!m) return true;
        if (m.indexOf("opus") >= 0 || m.indexOf("webm") >= 0 || m.indexOf("mp4") >= 0)
            return false;
        return (
            m.indexOf("pcm") >= 0 ||
            m.indexOf("l16") >= 0 ||
            m.indexOf("linear") >= 0
        );
    }

    function playModelAudioB64(base64, mimeType) {
        if (!base64 || !mimeLooksLikeRawPcm(mimeType)) return;
        ensureAudioContext()
            .then(function () {
                if (!audioCtx) return;
                var rate = parsePcmSampleRate(mimeType);
                var binary = atob(base64);
                var byteLen = binary.length;
                if (byteLen < 2) return;
                var raw = new Uint8Array(byteLen);
                for (var i = 0; i < byteLen; i++) raw[i] = binary.charCodeAt(i);
                var sampleCount = byteLen >> 1;
                var buffer = audioCtx.createBuffer(1, sampleCount, rate);
                var ch = buffer.getChannelData(0);
                var dv = new DataView(raw.buffer, raw.byteOffset, raw.byteLength);
                for (var s = 0; s < sampleCount; s++) {
                    ch[s] = dv.getInt16(s * 2, true) / 32768;
                }
                var src = audioCtx.createBufferSource();
                src.buffer = buffer;
                src.connect(audioCtx.destination);
                var startAt = Math.max(audioCtx.currentTime, nextAudioTime);
                src.onended = function () {
                    chefPcmSourcesPlaying -= 1;
                    if (chefPcmSourcesPlaying < 0) chefPcmSourcesPlaying = 0;
                    chefPcmTailUntil = performance.now() + CHEF_PCM_TAIL_MS;
                    if (handsFreeVoice && handsFreeVoice.onChefPcmProgress) {
                        handsFreeVoice.onChefPcmProgress();
                    }
                };
                src.start(startAt);
                chefPcmSourcesPlaying += 1;
                nextAudioTime = startAt + buffer.duration;
            })
            .catch(function () {});
    }

    function connectWs() {
        if (!sessionId) return;
        var gen = (wsGeneration += 1);
        if (ws) {
            try {
                ws.close();
            } catch (e) { /* ignore */ }
            ws = null;
        }
        try {
            ws = new WebSocket(wsUrl());
        } catch (e) {
            setWsStatus("WebSocket unavailable");
            return;
        }
        setWsStatus("Connecting…");
        ws.onopen = function () {
            if (gen !== wsGeneration) return;
            setWsStatus("Live ready");
        };
        ws.onclose = function () {
            if (gen !== wsGeneration) return;
            handsFreeVoice.onWsClosed();
            setWsStatus("Disconnected");
            if (sessionId && wsLiveReconnects < 2) {
                wsLiveReconnects += 1;
                setTimeout(function () {
                    if (!sessionId) return;
                    setWsStatus("Reconnecting…");
                    connectWs();
                }, 1500);
            }
        };
        ws.onerror = function () {
            if (gen !== wsGeneration) return;
            handsFreeVoice.resetChefGate();
            setWsStatus("Error");
        };
        ws.onmessage = function (ev) {
            if (gen !== wsGeneration) return;
            try {
                var msg = JSON.parse(ev.data);
            } catch (e) {
                return;
            }
            if (msg.type === "live_ready") {
                wsLiveReconnects = 0;
                resetChefPcmPlaybackTracking();
                setWsStatus("Chef online");
                handsFreeVoice.onLiveReady();
            } else if (msg.type === "model_audio" && msg.data) {
                handsFreeVoice.markChefModelActivity();
                playModelAudioB64(msg.data, msg.mime_type || msg.mimeType);
            } else if (msg.type === "model_text" && msg.text) {
                handsFreeVoice.markChefModelActivity();
                setChefStatus(msg.text);
            } else if (msg.type === "transcription" && msg.text) {
                if (msg.role !== "user") {
                    handsFreeVoice.markChefModelActivity();
                }
                setChefStatus(
                    (msg.role === "user" ? "You: " : "Chef: ") + msg.text,
                );
            } else if (msg.type === "tool_call") {
                handsFreeVoice.markChefModelActivity();
            } else if (msg.type === "kitchen_timer" && msg.duration_seconds) {
                showTimer(msg.duration_seconds);
            } else if (msg.type === "step_navigate" && msg.direction) {
                applyStepNavigate(msg.direction);
            } else if (msg.type === "error" && msg.message) {
                handsFreeVoice.resetChefGate();
                setWsStatus(msg.message);
            }
        };
    }

    function notifyStepChangedForVoice() {
        if (handsFreeVoice && handsFreeVoice.onStepUiChanged) {
            handsFreeVoice.onStepUiChanged();
        }
    }

    function applyStepNavigate(direction) {
        if (!steps.length) return;
        if (direction === "next") {
            if (stepIdx < steps.length - 1) {
                stepIdx += 1;
                renderStep();
                notifyStepChangedForVoice();
            }
        } else if (direction === "previous") {
            if (stepIdx > 0) {
                stepIdx -= 1;
                renderStep();
                notifyStepChangedForVoice();
            }
        }
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

    function getStepContextForWs() {
        if (!steps.length || stepIdx < 0 || stepIdx >= steps.length) {
            return {};
        }
        var s = steps[stepIdx];
        var recipeStepNo =
            s.step_number != null && s.step_number !== ""
                ? s.step_number
                : stepIdx + 1;
        return {
            step_number: recipeStepNo,
            ui_step_index: stepIdx + 1,
            total_steps: steps.length,
        };
    }

    function sendUserText(text) {
        if (!ws || ws.readyState !== WebSocket.OPEN) {
            setWsStatus("Connect the API (see README) to chat with the chef.");
            return;
        }
        var trimmed = String(text || "").trim();
        if (!trimmed) {
            return;
        }
        if (!handsFreeVoice.canSendChefPrompt()) {
            if (handsFreeVoice.getChefGateDebug) {
                agentLogVoiceGate("sendUserText_blocked", handsFreeVoice.getChefGateDebug());
            }
            setWsStatus("Wait for the chef to finish…");
            return;
        }
        handsFreeVoice.onUserPromptCommitted();
        var payload = { type: "user_text", text: trimmed };
        var ctx = getStepContextForWs();
        if (ctx.step_number != null) {
            payload.step_number = ctx.step_number;
            payload.ui_step_index = ctx.ui_step_index;
            payload.total_steps = ctx.total_steps;
        }
        ws.send(JSON.stringify(payload));
    }

    /**
     * After Live is ready, SpeechRecognition runs continuously: each new final transcript
     * is sent to the chef. Mic tap stops continuous capture for one push-to-talk utterance.
     * Dedupe ignores repeats within ~2s only when still on the same step (avoids drops after Next).
     */
    var handsFreeVoice = (function setupHandsFreeVoice() {
        var btn = document.getElementById("crave-voice-btn");
        var SR = window.SpeechRecognition || window.webkitSpeechRecognition;

        /** True from when we send a prompt until the first model chunk or failsafe. */
        var awaitingChefReply = false;
        /** True while model audio/text/tool chunks are arriving (gap detector). */
        var inChefStream = false;
        /** After the chef goes quiet, block prompts until this time (epoch ms). */
        var voiceBlockedUntil = 0;
        var chefStreamEndTimer = null;
        var chefReplyFailSafeTimer = null;
        /** Ms with no chef chunks before we treat the reply as finished. */
        var CHEF_STREAM_GAP_MS = 750;
        /** Brief pause after the network stream ends; PCM end is tracked separately via onended. */
        var AFTER_CHEF_PAUSE_MS = 650;
        /** If the server never emits model activity, unlock so the UI never deadlocks. */
        var CHEF_REPLY_FAILSAFE_MS = 90000;
        /** Unlock mic sooner when the chef sends nothing (no audio/tool/text). */
        var NO_MODEL_REPLY_UNLOCK_MS = 14000;
        var noModelUnlockTimer = null;

        function clearChefReplyFailSafe() {
            if (chefReplyFailSafeTimer) {
                clearTimeout(chefReplyFailSafeTimer);
                chefReplyFailSafeTimer = null;
            }
        }

        function clearNoModelUnlock() {
            if (noModelUnlockTimer) {
                clearTimeout(noModelUnlockTimer);
                noModelUnlockTimer = null;
            }
        }

        function finishChefReplyCycle() {
            clearNoModelUnlock();
            clearChefReplyFailSafe();
            if (chefStreamEndTimer) {
                clearTimeout(chefStreamEndTimer);
                chefStreamEndTimer = null;
            }
            awaitingChefReply = false;
            inChefStream = false;
            voiceBlockedUntil = Date.now() + AFTER_CHEF_PAUSE_MS;
            scheduleResumeWhenGateOpen();
        }

        function resetChefGate() {
            clearNoModelUnlock();
            clearChefReplyFailSafe();
            if (chefStreamEndTimer) {
                clearTimeout(chefStreamEndTimer);
                chefStreamEndTimer = null;
            }
            awaitingChefReply = false;
            inChefStream = false;
            voiceBlockedUntil = 0;
            scheduleResumeWhenGateOpen();
        }

        function onUserPromptCommitted() {
            clearNoModelUnlock();
            clearChefReplyFailSafe();
            if (chefStreamEndTimer) {
                clearTimeout(chefStreamEndTimer);
                chefStreamEndTimer = null;
            }
            awaitingChefReply = true;
            inChefStream = false;
            voiceBlockedUntil = 0;
            pauseRecBecauseChefOutput();
            noModelUnlockTimer = setTimeout(function () {
                noModelUnlockTimer = null;
                if (awaitingChefReply && !inChefStream) {
                    finishChefReplyCycle();
                    setWsStatus(
                        "No chef reply yet — speak again or tap a quick prompt",
                    );
                }
            }, NO_MODEL_REPLY_UNLOCK_MS);
            chefReplyFailSafeTimer = setTimeout(function () {
                chefReplyFailSafeTimer = null;
                finishChefReplyCycle();
            }, CHEF_REPLY_FAILSAFE_MS);
        }

        function markChefModelActivity() {
            clearNoModelUnlock();
            clearChefReplyFailSafe();
            awaitingChefReply = false;
            inChefStream = true;
            if (chefStreamEndTimer) {
                clearTimeout(chefStreamEndTimer);
            }
            chefStreamEndTimer = setTimeout(function () {
                finishChefReplyCycle();
            }, CHEF_STREAM_GAP_MS);
            pauseRecBecauseChefOutput();
        }

        function canSendChefPrompt() {
            return (
                !awaitingChefReply &&
                !inChefStream &&
                Date.now() >= voiceBlockedUntil &&
                !isChefTtsAudioPlaying()
            );
        }

        function getChefGateDebug() {
            return {
                awaitingChefReply: awaitingChefReply,
                inChefStream: inChefStream,
                voiceBlockedUntil: voiceBlockedUntil,
                now: Date.now(),
                ttsPlaying: isChefTtsAudioPlaying(),
                pcmSourcesPlaying: chefPcmSourcesPlaying,
                pcmTailUntil: chefPcmTailUntil,
                ctxState: audioCtx ? audioCtx.state : null,
                ctxTime: audioCtx ? audioCtx.currentTime : null,
                nextAudioTime: nextAudioTime,
            };
        }

        var lastSentStepIdx = -1;

        if (!SR) {
            if (btn) {
                btn.title =
                    "Voice needs Chrome or Edge (SpeechRecognition) on HTTPS or localhost";
                btn.disabled = true;
                btn.classList.add("opacity-40", "cursor-not-allowed");
            }
            return {
                onLiveReady: function () {
                    resetChefGate();
                },
                onWsClosed: function () {},
                markChefModelActivity: markChefModelActivity,
                onUserPromptCommitted: onUserPromptCommitted,
                resetChefGate: resetChefGate,
                onStepUiChanged: function () {
                    lastSentStepIdx = -1;
                },
                getChefGateDebug: getChefGateDebug,
                onChefPcmProgress: function () {},
                canSendChefPrompt: canSendChefPrompt,
                isVoiceSendAllowed: canSendChefPrompt,
            };
        }

        var rec = new SR();
        rec.lang = "en-US";
        rec.continuous = true;
        rec.interimResults = true;

        var manualSession = false;
        var handsFreeRunning = false;
        var restartTimer = null;
        var resumePollTimer = null;
        var lastSentAt = 0;
        var lastSentText = "";

        function clearResumePoll() {
            if (resumePollTimer) {
                clearTimeout(resumePollTimer);
                resumePollTimer = null;
            }
        }

        /** Stop the mic pipeline while chef audio may be in the room (no echo into SR). */
        function pauseRecBecauseChefOutput() {
            if (!handsFreeRunning) return;
            clearResumePoll();
            if (restartTimer) {
                clearTimeout(restartTimer);
                restartTimer = null;
            }
            try {
                rec.stop();
            } catch (e) {
                /* not running */
            }
        }

        /** Start hands-free listening only once prompts are allowed (after chef + tail + pause). */
        function scheduleResumeWhenGateOpen() {
            if (!handsFreeRunning || manualSession) return;
            if (restartTimer) {
                clearTimeout(restartTimer);
                restartTimer = null;
            }
            clearResumePoll();
            function tick() {
                resumePollTimer = null;
                if (!handsFreeRunning || manualSession || !ws || ws.readyState !== WebSocket.OPEN) {
                    return;
                }
                if (canSendChefPrompt()) {
                    try {
                        rec.continuous = true;
                        rec.interimResults = true;
                        rec.start();
                    } catch (e) {
                        resumePollTimer = setTimeout(tick, 220);
                        return;
                    }
                    setWsStatus("Chef online · mic always on");
                    return;
                }
                resumePollTimer = setTimeout(tick, 130);
            }
            resumePollTimer = setTimeout(tick, 60);
        }

        function normalizeSpace(s) {
            return (s || "").replace(/\s+/g, " ").trim();
        }

        function rowTranscript(row) {
            return (row && row[0] && row[0].transcript) || "";
        }

        function gatherNewFinalTranscript(ev) {
            var s = "";
            for (var i = ev.resultIndex; i < ev.results.length; i++) {
                if (ev.results[i].isFinal) {
                    s += rowTranscript(ev.results[i]);
                }
            }
            return normalizeSpace(s);
        }

        function currentUtteranceHypothesis(ev) {
            var t = "";
            for (var i = ev.resultIndex; i < ev.results.length; i++) {
                t += rowTranscript(ev.results[i]);
            }
            return normalizeSpace(t);
        }

        function scheduleRestartRec(delayMs) {
            if (restartTimer) clearTimeout(restartTimer);
            restartTimer = setTimeout(function () {
                restartTimer = null;
                scheduleResumeWhenGateOpen();
            }, delayMs || 280);
        }

        function sendVoiceCommand(displayText, payloadText) {
            if (!canSendChefPrompt()) {
                return;
            }
            var now = Date.now();
            var sameStep =
                typeof stepIdx === "number" && stepIdx === lastSentStepIdx;
            if (
                payloadText === lastSentText &&
                now - lastSentAt < 1800 &&
                sameStep
            ) {
                return;
            }
            setChefStatus('You said: "' + displayText + '"');
            sendUserText(payloadText);
            lastSentText = payloadText;
            lastSentAt = now;
            lastSentStepIdx = stepIdx;
            setWsStatus("Chef online · mic always on");
        }

        rec.onresult = function (ev) {
            if (manualSession) {
                var manualPiece = gatherNewFinalTranscript(ev);
                if (!manualPiece) return;
                sendVoiceCommand(manualPiece, manualPiece);
                return;
            }

            var lastIdx = ev.results.length - 1;
            if (lastIdx >= 0 && !ev.results[lastIdx].isFinal) {
                var hyp = currentUtteranceHypothesis(ev);
                if (hyp) {
                    if (inChefStream || awaitingChefReply) {
                        setWsStatus("Chef is replying…");
                    } else if (isChefTtsAudioPlaying()) {
                        setWsStatus("Chef audio playing — wait to speak (or use headphones)");
                    } else if (!canSendChefPrompt()) {
                        setWsStatus("Brief pause — then speak");
                    } else {
                        setWsStatus("Listening…");
                    }
                }
            }

            var piece = gatherNewFinalTranscript(ev);
            if (!piece) return;
            if (!canSendChefPrompt()) {
                agentLogVoiceGate("voice_final_blocked", getChefGateDebug());
                return;
            }

            sendVoiceCommand(piece, piece);
        };

        rec.onerror = function (ev) {
            if (ev && ev.error === "aborted") return;

            if (manualSession) {
                manualSession = false;
                rec.continuous = true;
                rec.interimResults = true;
                if (ev && ev.error === "not-allowed") {
                    handsFreeRunning = false;
                    setWsStatus("Mic blocked — tap mic once to enable");
                } else {
                    handsFreeRunning = true;
                    setWsStatus("Chef online · mic always on");
                }
                scheduleRestartRec(200);
                return;
            }

            if (ev && ev.error === "not-allowed") {
                handsFreeRunning = false;
                setWsStatus("Mic blocked — tap mic once to enable");
            } else if (ev && ev.error === "no-speech") {
                /* onend will restart */
            } else {
                setWsStatus("Mic error — tap mic or use quick prompts");
            }
        };

        rec.onend = function () {
            if (manualSession) {
                manualSession = false;
                rec.continuous = true;
                rec.interimResults = true;
                handsFreeRunning = true;
                setWsStatus("Chef online · mic always on");
                scheduleRestartRec(200);
                return;
            }
            if (handsFreeRunning && ws && ws.readyState === WebSocket.OPEN) {
                scheduleResumeWhenGateOpen();
            }
        };

        function startHandsFreeLoop() {
            if (handsFreeRunning) return;
            handsFreeRunning = true;
            lastSentText = "";
            lastSentStepIdx = -1;
            rec.continuous = true;
            rec.interimResults = true;
            try {
                rec.start();
                setWsStatus("Chef online · mic always on");
            } catch (e) {
                scheduleRestartRec(400);
            }
        }

        function stopHandsFreeLoop() {
            handsFreeRunning = false;
            manualSession = false;
            lastSentStepIdx = -1;
            resetChefGate();
            if (restartTimer) {
                clearTimeout(restartTimer);
                restartTimer = null;
            }
            clearResumePoll();
            try {
                rec.stop();
            } catch (e) { /* ignore */ }
        }

        if (btn) {
            btn.addEventListener("click", function (ev) {
                ev.stopPropagation();
                if (!ws || ws.readyState !== WebSocket.OPEN) {
                    setWsStatus("Wait for Chef online");
                    return;
                }
                if (!handsFreeVoice.canSendChefPrompt()) {
                    setWsStatus("Wait for the chef to finish…");
                    return;
                }
                ensureAudioContext().catch(function () {});
                manualSession = true;
                try {
                    rec.stop();
                } catch (e) { /* ignore */ }
                setTimeout(function () {
                    rec.continuous = false;
                    rec.interimResults = false;
                    setWsStatus("Listening… (one phrase)");
                    try {
                        rec.start();
                    } catch (err) {
                        manualSession = false;
                        setWsStatus("Tap again to speak");
                        scheduleRestartRec(300);
                    }
                }, 120);
            });
        }

        return {
            onLiveReady: function () {
                resetChefGate();
                startHandsFreeLoop();
            },
            onWsClosed: function () {
                stopHandsFreeLoop();
            },
            markChefModelActivity: markChefModelActivity,
            onUserPromptCommitted: onUserPromptCommitted,
            resetChefGate: resetChefGate,
            onStepUiChanged: function () {
                lastSentStepIdx = -1;
            },
            getChefGateDebug: getChefGateDebug,
            onChefPcmProgress: scheduleResumeWhenGateOpen,
            canSendChefPrompt: canSendChefPrompt,
            isVoiceSendAllowed: canSendChefPrompt,
        };
    })();

    if (btnPrev) {
        btnPrev.addEventListener("click", function () {
            if (stepIdx > 0) {
                stepIdx -= 1;
                renderStep();
                notifyStepChangedForVoice();
            }
        });
    }
    if (btnNext) {
        btnNext.addEventListener("click", function () {
            if (!steps.length) return;
            if (stepIdx < steps.length - 1) {
                stepIdx += 1;
                renderStep();
                notifyStepChangedForVoice();
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
