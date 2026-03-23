#!/usr/bin/env python3
"""
YTPoop LLM Music Video Generator — Web UI Backend
FastAPI server: audio analysis, configurable GPU rendering, preset management.
"""

import os, sys, json, threading, uuid, time
from pathlib import Path
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
import uvicorn

SCRIPT_DIR = Path(__file__).resolve().parent
STATIC_DIR = SCRIPT_DIR / "static"
OUTPUT_DIR = SCRIPT_DIR / "output"
PRESET_DIR = SCRIPT_DIR / "presets"
UPLOAD_DIR = SCRIPT_DIR / "uploads"
for d in [STATIC_DIR, OUTPUT_DIR, PRESET_DIR, UPLOAD_DIR]:
    d.mkdir(exist_ok=True)

# Import project modules
sys.path.insert(0, str(SCRIPT_DIR))
from step1_analyze import analyze
from step2_render import render as gpu_render, SEGMENT_REGISTRY


# ─── FastAPI app ─────────────────────────────────────────────────────────────

app = FastAPI(title="YTPoop LLM Music Video Generator")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/output", StaticFiles(directory=str(OUTPUT_DIR)), name="output")

render_tasks = {}  # task_id -> { progress, status, outputs }


@app.get("/")
async def root():
    return FileResponse(str(STATIC_DIR / "index.html"))


# ─── Audio Analysis ──────────────────────────────────────────────────────────

@app.post("/api/analyze")
async def analyze_audio(request: Request):
    form = await request.form()
    if "audio" not in form or not form["audio"].filename:
        return JSONResponse({"error": "No audio file"}, 400)

    f = form["audio"]
    dest = UPLOAD_DIR / f.filename
    dest.write_bytes(await f.read())

    try:
        fps = int(form.get("fps", 30))
        data = analyze(str(dest), fps=fps)

        # Save analysis JSON alongside the upload
        json_path = dest.with_suffix(".analysis.json")
        with open(json_path, "w", encoding="utf-8") as jf:
            json.dump(data, jf, ensure_ascii=False)

        return JSONResponse({
            "duration": data["duration"],
            "n_beats": data["n_beats"],
            "n_frames": data["n_frames"],
            "fps": data["fps"],
            "audio_path": str(dest),
            "analysis_path": str(json_path),
        })
    except Exception as e:
        return JSONResponse({"error": str(e)[:500]}, 500)


# ─── Segments ────────────────────────────────────────────────────────────────

@app.get("/api/segments")
async def get_segments():
    result = {}
    for key, info in SEGMENT_REGISTRY.items():
        result[key] = {
            "name": info["name"],
            "desc": info["desc"],
            "default_weight": info["default_weight"],
        }
    return JSONResponse(result)


# ─── Presets ─────────────────────────────────────────────────────────────────

@app.get("/api/presets")
async def list_presets():
    return JSONResponse(sorted([f.stem for f in PRESET_DIR.glob("*.json")]))


@app.post("/api/presets")
async def save_preset(request: Request):
    data = await request.json()
    name = data.get("name", "").strip()
    if not name:
        return JSONResponse({"message": "Enter a name"}, 400)
    path = PRESET_DIR / f"{name}.json"
    path.write_text(json.dumps(data.get("settings", {}), indent=2, ensure_ascii=False), encoding="utf-8")
    return JSONResponse({"message": f"Saved: {name}"})


@app.get("/api/presets/{name}")
async def load_preset(name: str):
    path = PRESET_DIR / f"{name}.json"
    if not path.exists():
        return JSONResponse({"error": "Not found"}, 404)
    data = json.loads(path.read_text(encoding="utf-8"))
    return JSONResponse({"settings": data})


@app.delete("/api/presets/{name}")
async def delete_preset(name: str):
    path = PRESET_DIR / f"{name}.json"
    if path.exists():
        path.unlink()
    return JSONResponse({"message": f"Deleted: {name}"})


# ─── Saved Content ───────────────────────────────────────────────────────────

SAVED_CONTENT_PATH = UPLOAD_DIR / "saved_content.json"

@app.get("/api/content")
async def load_content():
    if SAVED_CONTENT_PATH.exists():
        data = json.loads(SAVED_CONTENT_PATH.read_text(encoding="utf-8"))
        return JSONResponse(data)
    return JSONResponse({})

@app.post("/api/content")
async def save_content(request: Request):
    data = await request.json()
    SAVED_CONTENT_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return JSONResponse({"message": "Saved"})

@app.delete("/api/content")
async def clear_content():
    if SAVED_CONTENT_PATH.exists():
        SAVED_CONTENT_PATH.unlink()
    return JSONResponse({"message": "Cleared"})


# ─── Lyrics -> Ollama Content Generation ─────────────────────────────────────

@app.post("/api/generate-content")
async def generate_content(request: Request):
    """Use Ollama to generate visual content from lyrics/mood."""
    import httpx, re

    body = await request.json()
    lyrics = body.get("lyrics", "").strip()
    mood = body.get("mood", "").strip() or "match the lyrics"

    if not lyrics and not mood:
        return JSONResponse({"error": "Provide lyrics or mood"}, 400)

    lyrics_part = f"\nLyrics:\n{lyrics[:2000]}" if lyrics else ""

    prompt = f"""Generate content for a music video. Output ONLY valid JSON, no markdown, no explanation.

The JSON must have exactly 3 arrays:
- "impact_words": 30 short UPPERCASE words/phrases for big visual impact. Match the song language.
- "phrases": 25 short sentences (max 8 words). Match the song language and mood.
- "tech_lines": 15 short status-line strings that match the theme.

Song mood/theme: {mood}
{lyrics_part}

Output the JSON now:"""

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post("http://localhost:11434/api/generate", json={
                "model": "qwen2.5",
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.7, "num_predict": 4000},
            })
            resp.raise_for_status()
            result = resp.json()
            raw = result.get("response", "").strip()

            # Try direct parse first
            content = None
            try:
                content = json.loads(raw)
            except json.JSONDecodeError:
                # Strip markdown code fences
                cleaned = re.sub(r'```(?:json)?\s*', '', raw)
                cleaned = re.sub(r'```\s*$', '', cleaned)
                # Find JSON object
                match = re.search(r'\{[^{}]*(?:\[[^\]]*\][^{}]*)*\}', cleaned, re.DOTALL)
                if match:
                    try:
                        content = json.loads(match.group())
                    except json.JSONDecodeError:
                        pass

            if not content:
                # Last resort: try to extract arrays manually
                impact = re.findall(r'"([^"]{1,40})"', raw)
                if len(impact) >= 10:
                    content = {
                        "impact_words": [w.upper() for w in impact[:30]],
                        "phrases": impact[30:55] if len(impact) > 30 else impact[:25],
                        "tech_lines": impact[55:70] if len(impact) > 55 else impact[:15],
                    }

            if not content:
                return JSONResponse({
                    "error": f"Could not parse Ollama response. Raw (first 300 chars): {raw[:300]}"
                }, 500)

            return JSONResponse({
                "impact_words": content.get("impact_words", []),
                "phrases": content.get("phrases", []),
                "tech_lines": content.get("tech_lines", []),
            })

    except httpx.ConnectError:
        return JSONResponse({"error": "Cannot connect to Ollama. Is it running? (ollama serve)"}, 500)
    except Exception as e:
        return JSONResponse({"error": f"Ollama error: {str(e)[:300]}"}, 500)


# ─── Render ──────────────────────────────────────────────────────────────────

@app.post("/api/render")
async def start_render(request: Request):
    form = await request.form()
    settings = json.loads(form.get("settings", "{}"))

    # Save uploaded audio
    audio_path = None
    if "audio" in form and form["audio"].filename:
        f = form["audio"]
        dest = UPLOAD_DIR / f.filename
        dest.write_bytes(await f.read())
        audio_path = str(dest)
    elif settings.get("audio_path"):
        audio_path = settings["audio_path"]

    if not audio_path:
        return JSONResponse({"error": "No audio file"}, 400)

    # Save optional background image
    bg_image_path = None
    if "bg_image" in form and form["bg_image"].filename:
        f = form["bg_image"]
        dest = UPLOAD_DIR / f"bg_{f.filename}"
        dest.write_bytes(await f.read())
        bg_image_path = str(dest)

    # Save optional background video
    bg_video_path = None
    if "bg_video" in form and form["bg_video"].filename:
        f = form["bg_video"]
        dest = UPLOAD_DIR / f"bgvid_{f.filename}"
        dest.write_bytes(await f.read())
        bg_video_path = str(dest)

    # Inject bg paths into settings
    if bg_image_path:
        settings.setdefault("background", {})["image_path"] = bg_image_path
    if bg_video_path:
        settings.setdefault("background", {})["video_path"] = bg_video_path

    task_id = str(uuid.uuid4())[:8]
    render_tasks[task_id] = {"progress": 0, "status": "Preparing...", "outputs": []}

    def do_render():
        try:
            render_tasks[task_id]["status"] = "Analyzing audio..."
            render_tasks[task_id]["progress"] = 2

            # Check for existing analysis or run new one
            analysis_path = Path(audio_path).with_suffix(".analysis.json")
            if analysis_path.exists():
                with open(analysis_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # Verify audio_path matches
                if data.get("audio_path") != str(Path(audio_path).resolve()):
                    data = analyze(audio_path, fps=settings.get("output", {}).get("fps", 30))
            else:
                data = analyze(audio_path, fps=settings.get("output", {}).get("fps", 30))

            render_tasks[task_id]["status"] = "Rendering video..."
            render_tasks[task_id]["progress"] = 5

            out_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{Path(audio_path).stem.replace(' ','_')[:80]}.mp4"
            out_path = str(OUTPUT_DIR / out_name)

            def on_progress(pct):
                # Map render progress 0-100 to task progress 5-98
                render_tasks[task_id]["progress"] = int(5 + pct * 0.93)
                render_tasks[task_id]["status"] = f"Rendering... {pct:.0f}%"

            max_dur = settings.get("max_duration", None)
            if max_dur:
                max_dur = float(max_dur)
            gpu_render(data, out_path, max_dur=max_dur, settings=settings, progress_cb=on_progress)

            render_tasks[task_id]["outputs"].append(out_name)
            render_tasks[task_id]["progress"] = 100
            render_tasks[task_id]["status"] = "Done!"

        except Exception as e:
            import traceback
            traceback.print_exc()
            render_tasks[task_id]["status"] = f"Error: {str(e)[:500]}"
            render_tasks[task_id]["progress"] = -1

    thread = threading.Thread(target=do_render, daemon=True)
    thread.start()
    return JSONResponse({"taskId": task_id})


@app.get("/api/render/{task_id}")
async def render_status(task_id: str):
    task = render_tasks.get(task_id)
    if not task:
        return JSONResponse({"error": "Not found"}, 404)
    return JSONResponse(task)


# ─── Launch ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import webbrowser
    print("\n  YTPoop LLM Music Video Generator")
    print("  http://localhost:7861\n")
    webbrowser.open("http://localhost:7861")
    uvicorn.run(app, host="0.0.0.0", port=7861, log_level="info")
