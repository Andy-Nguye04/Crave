/**
 * Crave Audio Engine — Web Speech API for mic input + PCM playback for Gemini output.
 *
 * Uses the browser's built-in speech recognition for hands-free voice input,
 * and scheduled AudioBufferSourceNodes for gapless Gemini audio playback (PCM 16-bit 24kHz).
 *
 * Usage:
 *   var audio = new CraveAudio();
 *   await audio.init();            // set up speech recognition + playback context
 *   audio.attachWs(ws);            // wire to an open WebSocket
 *   audio.start();                 // begin listening + playback
 *   audio.stop();                  // tear down everything
 *   audio.onTranscript = fn;       // callback for interim/final transcripts
 */
(function () {
    "use strict";

    var OUTPUT_SAMPLE_RATE = 24000;

    function CraveAudio() {
        this.ws = null;
        this.playbackCtx = null;
        this.recognition = null;
        this.isMuted = false;
        this.isStarted = false;
        this.playbackTime = 0;
        this.onTranscript = null; // callback(text, isFinal)
    }

    /**
     * Set up speech recognition and audio playback context.
     * Must be called from a user gesture (click handler).
     */
    CraveAudio.prototype.init = async function () {
        // Playback context at 24kHz for Gemini output
        this.playbackCtx = new AudioContext({ sampleRate: OUTPUT_SAMPLE_RATE });

        // Set up Web Speech API for speech-to-text
        var SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SpeechRecognition) {
            console.warn("CraveAudio: Web Speech API not supported in this browser");
            return;
        }

        this.recognition = new SpeechRecognition();
        this.recognition.continuous = true;
        this.recognition.interimResults = true;
        this.recognition.lang = "en-US";
        this.recognition.maxAlternatives = 1;

        var self = this;

        this.recognition.onresult = function (event) {
            if (self.isMuted || !self.isStarted) return;

            // Get the latest result
            var lastIdx = event.results.length - 1;
            var result = event.results[lastIdx];
            var transcript = result[0].transcript.trim();
            var isFinal = result.isFinal;

            if (!transcript) return;

            // Notify UI of transcript
            if (self.onTranscript) {
                self.onTranscript(transcript, isFinal);
            }

            // Only send final transcripts to the server
            if (isFinal && self.ws && self.ws.readyState === WebSocket.OPEN) {
                self.ws.send(JSON.stringify({
                    type: "speech_text",
                    text: transcript,
                }));
            }
        };

        this.recognition.onerror = function (event) {
            console.warn("CraveAudio: speech recognition error:", event.error);
            // Auto-restart on recoverable errors
            if (event.error === "no-speech" || event.error === "aborted" || event.error === "network") {
                if (self.isStarted && !self.isMuted) {
                    setTimeout(function () {
                        self._startRecognition();
                    }, 300);
                }
            }
        };

        this.recognition.onend = function () {
            // Continuous recognition can end unexpectedly — restart if still active
            if (self.isStarted && !self.isMuted) {
                setTimeout(function () {
                    self._startRecognition();
                }, 200);
            }
        };

        // Request mic permission via getUserMedia so the permission prompt shows
        // (some browsers need this before SpeechRecognition will work)
        try {
            var stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            // Immediately release the stream — we only needed the permission
            stream.getTracks().forEach(function (t) { t.stop(); });
        } catch (err) {
            console.warn("CraveAudio: mic permission denied:", err);
        }
    };

    /**
     * Wire the audio engine to an open WebSocket.
     */
    CraveAudio.prototype.attachWs = function (ws) {
        this.ws = ws;
    };

    /**
     * Begin speech recognition and enable playback.
     */
    CraveAudio.prototype.start = function () {
        this.isStarted = true;
        this.playbackTime = 0;

        if (this.playbackCtx && this.playbackCtx.state === "suspended") {
            this.playbackCtx.resume();
        }

        this._startRecognition();
    };

    CraveAudio.prototype._startRecognition = function () {
        if (!this.recognition || !this.isStarted || this.isMuted) return;
        try {
            this.recognition.start();
        } catch (e) {
            // Already started — ignore
        }
    };

    /**
     * Stop everything and release resources.
     */
    CraveAudio.prototype.stop = function () {
        this.isStarted = false;
        if (this.recognition) {
            try { this.recognition.stop(); } catch (_) {}
        }
        if (this.playbackCtx) this.playbackCtx.close().catch(function () {});
    };

    CraveAudio.prototype.toggleMute = function () {
        this.isMuted = !this.isMuted;
        if (this.recognition) {
            if (this.isMuted) {
                try { this.recognition.stop(); } catch (_) {}
            } else {
                this._startRecognition();
            }
        }
        return this.isMuted;
    };

    /**
     * Play a chunk of PCM 16-bit audio from Gemini.
     * Chunks are scheduled back-to-back for gapless playback.
     */
    CraveAudio.prototype.playChunk = function (pcmArrayBuffer) {
        if (!this.playbackCtx || this.playbackCtx.state === "closed") return;

        var int16 = new Int16Array(pcmArrayBuffer);
        if (int16.length === 0) return;

        var float32 = new Float32Array(int16.length);
        for (var i = 0; i < int16.length; i++) {
            float32[i] = int16[i] / 32768;
        }

        var buffer = this.playbackCtx.createBuffer(1, float32.length, OUTPUT_SAMPLE_RATE);
        buffer.copyToChannel(float32, 0);

        var source = this.playbackCtx.createBufferSource();
        source.buffer = buffer;
        source.connect(this.playbackCtx.destination);

        var now = this.playbackCtx.currentTime;
        var startAt = Math.max(now + 0.01, this.playbackTime);
        source.start(startAt);
        this.playbackTime = startAt + buffer.duration;
    };

    window.CraveAudio = CraveAudio;
})();
