/* ─── YTPoop LLM MV Generator — Frontend Logic ─── */

let segmentsInfo = {};  // populated from /api/segments
let audioPath = null;
let analysisPath = null;
let pollTimer = null;

// ─── Init ────────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", async () => {
    await loadSegments();
    await loadPresetList();
    updateColorPreview();

    document.getElementById("paletteSelect").addEventListener("change", onPaletteChange);
    ["color1","color2","color3","color4"].forEach(id => {
        document.getElementById(id).addEventListener("input", updateColorPreview);
    });

    document.getElementById("audioFile").addEventListener("change", uploadAndAnalyze);
    document.getElementById("generateBtn").addEventListener("click", () => startRender(0));
    document.getElementById("previewBtn").addEventListener("click", () => startRender(10));
    document.getElementById("presetSave").addEventListener("click", savePreset);
    document.getElementById("presetLoad").addEventListener("click", loadPreset);
    document.getElementById("presetDelete").addEventListener("click", deletePreset);
    document.getElementById("generateContentBtn").addEventListener("click", generateContentFromLyrics);
    document.getElementById("saveTextBtn").addEventListener("click", saveTextContent);
    document.getElementById("loadTextBtn").addEventListener("click", loadTextContent);
    document.getElementById("clearTextBtn").addEventListener("click", clearTextContent);
    // Auto-load saved content on startup
    loadTextContent(true);
    document.getElementById("bgOpacity").addEventListener("input", (e) => {
        document.getElementById("bgOpacityVal").textContent = parseFloat(e.target.value).toFixed(2);
    });
    document.getElementById("bgBrightness").addEventListener("input", (e) => {
        document.getElementById("bgBrightnessVal").textContent = parseFloat(e.target.value).toFixed(2);
    });
});


// ─── Segments ────────────────────────────────────────────────────────────────

async function loadSegments() {
    try {
        const res = await fetch("/api/segments");
        segmentsInfo = await res.json();
        renderSegmentList();
    } catch (e) {
        console.error("Failed to load segments:", e);
    }
}

function renderSegmentList() {
    const container = document.getElementById("segmentList");
    container.innerHTML = "";
    for (const [key, info] of Object.entries(segmentsInfo)) {
        const div = document.createElement("div");
        div.className = "segment-item";
        div.innerHTML = `
            <input type="checkbox" id="seg_${key}" data-seg="${key}" checked>
            <div style="flex:1">
                <div class="seg-name">${info.name}</div>
                <div class="seg-desc">${info.desc}</div>
            </div>
            <input type="range" min="0.01" max="0.30" step="0.01"
                   value="${info.default_weight}" id="segw_${key}" data-seg="${key}">
            <span class="seg-weight-val" id="segwv_${key}">${info.default_weight.toFixed(2)}</span>
        `;
        container.appendChild(div);

        document.getElementById(`segw_${key}`).addEventListener("input", (e) => {
            document.getElementById(`segwv_${key}`).textContent = parseFloat(e.target.value).toFixed(2);
        });
    }
}


// ─── Color palette ───────────────────────────────────────────────────────────

const PALETTE_COLORS = {
    neon:        ["#00ff41", "#ff0064", "#00c8ff", "#ffff00"],
    pastel:      ["#ffb6c1", "#b0e0e6", "#dda0dd", "#ffdab9"],
    monochrome:  ["#ffffff", "#c8c8c8", "#a0a0a0", "#787878"],
    cyberpunk:   ["#ff0080", "#00ffff", "#ff00ff", "#8000ff"],
    vaporwave:   ["#ff71ce", "#01cdfe", "#b967ff", "#05ff9d"],
    custom:      null,
};

function onPaletteChange() {
    const sel = document.getElementById("paletteSelect").value;
    const colors = PALETTE_COLORS[sel];
    if (colors) {
        ["color1","color2","color3","color4"].forEach((id, i) => {
            document.getElementById(id).value = colors[i];
        });
    }
    updateColorPreview();
}

function updateColorPreview() {
    const strip = document.getElementById("colorPreviewStrip");
    strip.innerHTML = "";
    ["color1","color2","color3","color4"].forEach(id => {
        const c = document.getElementById(id).value;
        const swatch = document.createElement("div");
        swatch.className = "swatch";
        swatch.style.background = c;
        strip.appendChild(swatch);
    });
}


// ─── Audio upload & analysis ─────────────────────────────────────────────────

async function uploadAndAnalyze() {
    const fileInput = document.getElementById("audioFile");
    if (!fileInput.files.length) return;

    const infoBox = document.getElementById("audioInfo");
    infoBox.innerHTML = "Analyzing...";

    const formData = new FormData();
    formData.append("audio", fileInput.files[0]);

    try {
        const res = await fetch("/api/analyze", { method: "POST", body: formData });
        const data = await res.json();
        if (data.error) {
            infoBox.innerHTML = `<span style="color:var(--danger)">${data.error}</span>`;
            return;
        }
        audioPath = data.audio_path;
        analysisPath = data.analysis_path;
        infoBox.innerHTML = `
            <strong>Duration:</strong> ${data.duration.toFixed(1)}s &nbsp;
            <strong>Beats:</strong> ${data.n_beats} &nbsp;
            <strong>Frames:</strong> ${data.n_frames} @ ${data.fps}fps
        `;
        document.getElementById("generateBtn").disabled = false;
        document.getElementById("previewBtn").disabled = false;
    } catch (e) {
        infoBox.innerHTML = `<span style="color:var(--danger)">Upload failed: ${e.message}</span>`;
    }
}


// ─── Read / Apply settings ───────────────────────────────────────────────────

function readSettings() {
    // Colors
    const palette = document.getElementById("paletteSelect").value;
    const primary = ["color1","color2","color3","color4"].map(id =>
        document.getElementById(id).value
    );

    // Segments
    const enabled = [];
    const weights = {};
    for (const key of Object.keys(segmentsInfo)) {
        const cb = document.getElementById(`seg_${key}`);
        if (cb && cb.checked) {
            enabled.push(key);
            const slider = document.getElementById(`segw_${key}`);
            weights[key] = parseFloat(slider.value);
        }
    }

    // Effects
    const effects = {};
    ["text_overlays","bloom","scanlines","vhs_glitch","chromatic_aberration","vignette","beat_flash"].forEach(id => {
        const el = document.getElementById(`fx_${id}`);
        effects[id] = el ? el.checked : true;
    });

    // Background
    const bgOpacity = parseFloat(document.getElementById("bgOpacity").value);
    const bgBrightness = parseFloat(document.getElementById("bgBrightness").value);

    // Content (lyrics-generated or custom)
    const content = {};
    const impactText = document.getElementById("customImpact").value.trim();
    const phrasesText = document.getElementById("customPhrases").value.trim();
    const techText = document.getElementById("customTech").value.trim();
    if (impactText) content.impact_words = impactText.split("\n").map(s => s.trim()).filter(Boolean);
    if (phrasesText) content.phrases = phrasesText.split("\n").map(s => s.trim()).filter(Boolean);
    if (techText) content.tech_lines = techText.split("\n").map(s => s.trim()).filter(Boolean);

    // Output
    const resSel = document.getElementById("resolutionSelect").value.split("x");
    const fps = parseInt(document.getElementById("fpsSelect").value);
    const codec = document.getElementById("codecSelect").value;

    return {
        colors: { primary, palette },
        segments: { enabled, weights },
        effects,
        background: { image_path: null, video_path: null, opacity: bgOpacity, brightness: bgBrightness },
        content,
        output: { width: parseInt(resSel[0]), height: parseInt(resSel[1]), fps, codec },
        audio_path: audioPath,
    };
}

function applySettings(s) {
    if (!s) return;

    // Colors
    if (s.colors) {
        if (s.colors.palette) document.getElementById("paletteSelect").value = s.colors.palette;
        if (s.colors.primary) {
            ["color1","color2","color3","color4"].forEach((id, i) => {
                if (s.colors.primary[i]) document.getElementById(id).value = s.colors.primary[i];
            });
        }
        updateColorPreview();
    }

    // Segments
    if (s.segments) {
        for (const key of Object.keys(segmentsInfo)) {
            const cb = document.getElementById(`seg_${key}`);
            if (cb) cb.checked = s.segments.enabled ? s.segments.enabled.includes(key) : true;
            const slider = document.getElementById(`segw_${key}`);
            if (slider && s.segments.weights && s.segments.weights[key] !== undefined) {
                slider.value = s.segments.weights[key];
                const lbl = document.getElementById(`segwv_${key}`);
                if (lbl) lbl.textContent = s.segments.weights[key].toFixed(2);
            }
        }
    }

    // Effects
    if (s.effects) {
        for (const [key, val] of Object.entries(s.effects)) {
            const el = document.getElementById(`fx_${key}`);
            if (el) el.checked = val;
        }
    }

    // Background
    if (s.background) {
        document.getElementById("bgOpacity").value = s.background.opacity || 0.3;
        document.getElementById("bgOpacityVal").textContent = (s.background.opacity || 0.3).toFixed(2);
        document.getElementById("bgBrightness").value = s.background.brightness || 1.0;
        document.getElementById("bgBrightnessVal").textContent = (s.background.brightness || 1.0).toFixed(2);
    }

    // Content
    if (s.content) {
        if (s.content.impact_words) document.getElementById("customImpact").value = s.content.impact_words.join("\n");
        if (s.content.phrases) document.getElementById("customPhrases").value = s.content.phrases.join("\n");
        if (s.content.tech_lines) document.getElementById("customTech").value = s.content.tech_lines.join("\n");
    }

    // Output
    if (s.output) {
        document.getElementById("resolutionSelect").value = `${s.output.width || 1920}x${s.output.height || 1080}`;
        document.getElementById("fpsSelect").value = s.output.fps || 30;
        document.getElementById("codecSelect").value = s.output.codec || "h264_nvenc";
    }
}


// ─── Render ──────────────────────────────────────────────────────────────────

async function startRender(maxDuration) {
    if (!audioPath) {
        alert("Upload an audio file first.");
        return;
    }

    document.getElementById("generateBtn").disabled = true;
    document.getElementById("previewBtn").disabled = true;

    const settings = readSettings();
    if (maxDuration > 0) {
        settings.max_duration = maxDuration;
    }
    const formData = new FormData();
    formData.append("settings", JSON.stringify(settings));

    // Attach audio file
    const audioFile = document.getElementById("audioFile").files[0];
    if (audioFile) {
        formData.append("audio", audioFile);
    }

    // Attach optional bg files
    const bgImageFile = document.getElementById("bgImageFile").files[0];
    if (bgImageFile) formData.append("bg_image", bgImageFile);

    const bgVideoFile = document.getElementById("bgVideoFile").files[0];
    if (bgVideoFile) formData.append("bg_video", bgVideoFile);

    // Reset UI
    setProgress(0, "Starting...");
    document.getElementById("outputLinks").innerHTML = "";

    try {
        const res = await fetch("/api/render", { method: "POST", body: formData });
        const data = await res.json();
        if (data.error) {
            setProgress(0, `Error: ${data.error}`);
            btn.disabled = false;
            return;
        }
        pollProgress(data.taskId);
    } catch (e) {
        setProgress(0, `Error: ${e.message}`);
        btn.disabled = false;
    }
}

function pollProgress(taskId) {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(async () => {
        try {
            const res = await fetch(`/api/render/${taskId}`);
            const data = await res.json();
            if (data.error) {
                clearInterval(pollTimer);
                setProgress(0, data.error);
                document.getElementById("generateBtn").disabled = false;
            document.getElementById("previewBtn").disabled = false;
                return;
            }

            const pct = Math.max(0, data.progress);
            setProgress(pct, data.status);

            if (data.progress >= 100) {
                clearInterval(pollTimer);
                document.getElementById("generateBtn").disabled = false;
            document.getElementById("previewBtn").disabled = false;
                // Show output links
                const container = document.getElementById("outputLinks");
                container.innerHTML = "";
                (data.outputs || []).forEach(name => {
                    const a = document.createElement("a");
                    a.href = `/output/${name}`;
                    a.textContent = name;
                    a.target = "_blank";
                    a.download = name;
                    container.appendChild(a);
                });
            } else if (data.progress < 0) {
                clearInterval(pollTimer);
                document.getElementById("generateBtn").disabled = false;
            document.getElementById("previewBtn").disabled = false;
            }
        } catch (e) {
            console.error("Poll error:", e);
        }
    }, 1000);
}

function setProgress(pct, status) {
    document.getElementById("progressBar").style.width = `${Math.max(0, pct)}%`;
    document.getElementById("progressStatus").textContent = status || "";
}


// ─── Presets ─────────────────────────────────────────────────────────────────

async function loadPresetList() {
    try {
        const res = await fetch("/api/presets");
        const names = await res.json();
        const sel = document.getElementById("presetSelect");
        sel.innerHTML = '<option value="">-- select --</option>';
        names.forEach(n => {
            const opt = document.createElement("option");
            opt.value = n; opt.textContent = n;
            sel.appendChild(opt);
        });
    } catch (e) {
        console.error("Failed to load presets:", e);
    }
}

async function savePreset() {
    const name = prompt("Preset name:");
    if (!name) return;
    const settings = readSettings();
    // Remove transient paths
    delete settings.audio_path;
    try {
        const res = await fetch("/api/presets", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name, settings }),
        });
        const data = await res.json();
        alert(data.message);
        await loadPresetList();
    } catch (e) {
        alert("Save failed: " + e.message);
    }
}

async function loadPreset() {
    const name = document.getElementById("presetSelect").value;
    if (!name) return;
    try {
        const res = await fetch(`/api/presets/${encodeURIComponent(name)}`);
        const data = await res.json();
        if (data.settings) {
            applySettings(data.settings);
        }
    } catch (e) {
        alert("Load failed: " + e.message);
    }
}

async function deletePreset() {
    const name = document.getElementById("presetSelect").value;
    if (!name) return;
    if (!confirm(`Delete preset "${name}"?`)) return;
    try {
        await fetch(`/api/presets/${encodeURIComponent(name)}`, { method: "DELETE" });
        await loadPresetList();
    } catch (e) {
        alert("Delete failed: " + e.message);
    }
}


// ─── Save / Load / Clear Text Content ────────────────────────────────────────

async function saveTextContent() {
    const data = {};
    const impact = document.getElementById("customImpact").value.trim();
    const phrases = document.getElementById("customPhrases").value.trim();
    const tech = document.getElementById("customTech").value.trim();
    if (impact) data.impact_words = impact.split("\n").map(s => s.trim()).filter(Boolean);
    if (phrases) data.phrases = phrases.split("\n").map(s => s.trim()).filter(Boolean);
    if (tech) data.tech_lines = tech.split("\n").map(s => s.trim()).filter(Boolean);

    try {
        await fetch("/api/content", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(data),
        });
        document.getElementById("textSaveStatus").textContent = "Saved!";
        setTimeout(() => document.getElementById("textSaveStatus").textContent = "", 2000);
    } catch (e) {
        document.getElementById("textSaveStatus").textContent = "Save failed.";
    }
}

async function loadTextContent(silent) {
    try {
        const res = await fetch("/api/content");
        const data = await res.json();
        if (data.impact_words) document.getElementById("customImpact").value = data.impact_words.join("\n");
        if (data.phrases) document.getElementById("customPhrases").value = data.phrases.join("\n");
        if (data.tech_lines) document.getElementById("customTech").value = data.tech_lines.join("\n");
        if (!silent) {
            document.getElementById("textSaveStatus").textContent = "Loaded!";
            setTimeout(() => document.getElementById("textSaveStatus").textContent = "", 2000);
        }
    } catch (e) {
        if (!silent) document.getElementById("textSaveStatus").textContent = "No saved content.";
    }
}

async function clearTextContent() {
    if (!confirm("Clear all text content?")) return;
    document.getElementById("customImpact").value = "";
    document.getElementById("customPhrases").value = "";
    document.getElementById("customTech").value = "";
    try {
        await fetch("/api/content", { method: "DELETE" });
    } catch (e) {}
    document.getElementById("textSaveStatus").textContent = "Cleared — will use defaults.";
    setTimeout(() => document.getElementById("textSaveStatus").textContent = "", 2000);
}


// ─── Lyrics -> Ollama Content Generation ────────────────────────────────────

async function generateContentFromLyrics() {
    const lyrics = document.getElementById("lyricsText").value.trim();
    const mood = document.getElementById("songMood").value.trim();
    const statusEl = document.getElementById("contentStatus");

    if (!lyrics) {
        statusEl.textContent = "Paste lyrics first.";
        return;
    }

    statusEl.innerHTML = '<span style="color:var(--accent)">Generating content via Ollama...</span>';
    document.getElementById("generateContentBtn").disabled = true;

    try {
        const res = await fetch("/api/generate-content", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ lyrics, mood }),
        });
        const data = await res.json();
        if (data.error) {
            statusEl.innerHTML = `<span style="color:var(--danger)">${data.error}</span>`;
            return;
        }
        // Fill the textareas
        if (data.impact_words) {
            document.getElementById("customImpact").value = data.impact_words.join("\n");
        }
        if (data.phrases) {
            document.getElementById("customPhrases").value = data.phrases.join("\n");
        }
        if (data.tech_lines) {
            document.getElementById("customTech").value = data.tech_lines.join("\n");
        }
        statusEl.innerHTML = `<span style="color:var(--accent)">Generated ${(data.impact_words||[]).length} impact words, ${(data.phrases||[]).length} phrases, ${(data.tech_lines||[]).length} tech lines</span>`;
    } catch (e) {
        statusEl.innerHTML = `<span style="color:var(--danger)">Ollama error: ${e.message}. Is Ollama running?</span>`;
    } finally {
        document.getElementById("generateContentBtn").disabled = false;
    }
}
