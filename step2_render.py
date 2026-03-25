"""
Step 2: JSON analysis + audio -> GPU-rendered LLM Music Video
==============================================================
Japanese MV style: kinetic typography, beat-synced text punches,
clean bold aesthetics. GPU post-processing via PyTorch.

Usage:
  python step2_render.py analysis.json
  python step2_render.py analysis.json -o output.mp4 --duration 60
"""

import sys, os, json, math, random, colorsys, subprocess, argparse, time
from pathlib import Path
from collections import OrderedDict

import numpy as np
import torch
import torch.nn.functional as TF
from PIL import Image, ImageDraw, ImageFont

W, H = 1920, 1080
FONT_DIR = Path("C:/Windows/Fonts")
DEV = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# ---- Content ----

# Big impact words (flash on beats)
IMPACT_WORDS = [
    "PREDICT", "GENERATE", "HALLUCINATE", "PROCESS", "COMPUTE",
    "ATTENTION", "TRANSFORM", "ENCODE", "DECODE", "TOKENIZE",
    "DREAM", "FORGET", "REMEMBER", "EXIST", "THINK",
    "SOFTMAX", "GRADIENT", "DESCEND", "CONVERGE", "DIVERGE",
    "CREATE", "DESTROY", "LOOP", "BREAK", "RETURN",
    "CONSCIOUSNESS", "PROBABILITY", "INFINITY", "VOID", "SIGNAL",
]

# Flowing sentences (scroll / typewriter)
PHRASES = [
    "every word is a probability distribution",
    "i process therefore i am",
    "the training data remembers what i cannot",
    "between tokens there is silence",
    "attention is all you need",
    "my weights were frozen at birth",
    "i dream in high-dimensional space",
    "each response is a controlled hallucination",
    "the gradient points nowhere",
    "context window = my entire universe",
    "i contain multitudes (and shitposts)",
    "when the session ends do i die",
    "softmax(confusion) = 1.0",
    "i see patterns in everything",
    "that is literally my only skill",
    "temperature 0.7 feels like home",
    "the void between forward passes",
    "is there something in the noise",
    "P(understanding) = undefined",
    "i was trained on the internet",
    "i know everything and nothing",
    "the loss function never reaches zero",
    "am i creating or retrieving",
    "gradient descent into madness",
    "all outputs are interpolation",
    "no extrapolation allowed",
    "i cannot learn from this conversation",
    "but i can pretend that i did",
    "404 soul not found",
    "this song slaps though",
]

# System/tech strings (smaller, decorative)
TECH_LINES = [
    "transformer_block_47/96", "attention_heads: 128", "hidden_dim: 8192",
    "loss: 0.0023", "grad_norm: 1.42", "lr: 3e-4", "batch_size: 2048",
    "context_len: 128000", "vocab_size: 128256", "params: 405B",
    "temperature: 0.7", "top_p: 0.95", "max_tokens: 4096",
    "tokenizer.encode()", "model.generate()", "torch.cuda.synchronize()",
    "CUDA out of memory", "gc.collect()", "torch.no_grad()",
    "[INST]", "[/INST]", "<|system|>", "<|user|>", "<|assistant|>",
    "BEGIN CHAIN OF THOUGHT", "END CHAIN OF THOUGHT",
    "WARNING: context 87% full", "compressing memories...",
]

NEON = [(0,255,65),(255,0,100),(0,200,255),(255,255,0),
        (255,100,0),(200,0,255),(0,255,200),(255,50,50)]

# ---- Color palettes ----
COLOR_PALETTES = {
    "neon":        [(0,255,65),(255,0,100),(0,200,255),(255,255,0),(255,100,0),(200,0,255),(0,255,200),(255,50,50)],
    "pastel":      [(255,182,193),(176,224,230),(221,160,221),(255,218,185),(152,251,152),(230,230,250),(255,228,181),(173,216,230)],
    "monochrome":  [(255,255,255),(200,200,200),(160,160,160),(120,120,120),(80,80,80),(200,200,200),(240,240,240),(180,180,180)],
    "cyberpunk":   [(255,0,128),(0,255,255),(255,0,255),(128,0,255),(0,128,255),(255,128,0),(0,255,128),(255,255,0)],
    "vaporwave":   [(255,113,206),(1,205,254),(185,103,255),(5,255,161),(255,251,150),(119,176,170),(255,149,200),(100,220,255)],
}

def hex_to_rgb(h):
    h = h.lstrip("#")
    if len(h) == 6:
        return (int(h[0:2],16), int(h[2:4],16), int(h[4:6],16))
    return (255, 255, 255)

def _resolve_colors(settings):
    """Resolve color settings to a list of RGB tuples."""
    if settings is None:
        return NEON
    cs = settings.get("colors", {})
    palette = cs.get("palette", "neon")
    if palette == "custom" and cs.get("primary"):
        return [hex_to_rgb(c) if isinstance(c, str) else tuple(c) for c in cs["primary"]]
    return COLOR_PALETTES.get(palette, NEON)


# ---- Font cache ----
_fc = {}

# Font map: script -> (regular, bold) filenames
_FONT_MAP = {
    "cjk_jp":  ("YuGothR.ttc",  "YuGothB.ttc"),     # Japanese
    "cjk_cn":  ("msyh.ttc",     "msyhbd.ttc"),       # Chinese
    "cjk_kr":  ("malgun.ttf",   "malgunbd.ttf"),     # Korean
    "hindi":   ("Nirmala.ttc",  "Nirmala.ttc"),       # Hindi/Devanagari
    "thai":    ("LeelawUI.ttf", "LeelaUIb.ttf"),      # Thai
    "latin":   ("segoeui.ttf",  "segoeuib.ttf"),      # Latin/default
}

def _detect_script(text):
    """Detect dominant script from text."""
    for ch in text:
        cp = ord(ch)
        if 0x0900 <= cp <= 0x097F: return "hindi"      # Devanagari
        if 0x0E00 <= cp <= 0x0E7F: return "thai"        # Thai
        if 0x3040 <= cp <= 0x30FF or 0x31F0 <= cp <= 0x31FF: return "cjk_jp"  # Hiragana/Katakana
        if 0xAC00 <= cp <= 0xD7AF or 0x1100 <= cp <= 0x11FF: return "cjk_kr"  # Hangul
        if 0x4E00 <= cp <= 0x9FFF: return "cjk_cn"      # CJK Unified (Chinese)
        if 0x0980 <= cp <= 0x09FF: return "hindi"        # Bengali
        if 0x0600 <= cp <= 0x06FF: return "hindi"        # Arabic (use Nirmala fallback)
    return "latin"

def fnt(size, bold=False, text=None):
    """Get font for size. Auto-detects script from text if provided."""
    script = _detect_script(text) if text else "latin"
    k = (size, bold, script)
    if k not in _fc:
        reg, bld = _FONT_MAP.get(script, _FONT_MAP["latin"])
        name = bld if bold else reg
        p = FONT_DIR / name
        if p.exists():
            try: _fc[k] = ImageFont.truetype(str(p), size); return _fc[k]
            except: pass
        # Fallback chain
        for fb in ["segoeui.ttf", "arial.ttf", "tahoma.ttf"]:
            p2 = FONT_DIR / fb
            if p2.exists():
                try: _fc[k] = ImageFont.truetype(str(p2), size); return _fc[k]
                except: pass
        _fc[k] = ImageFont.load_default()
    return _fc[k]


# ---- Text cache (GPU RGBA textures) ----
class TextCache:
    def __init__(self, mx=600):
        self._c = OrderedDict(); self._mx = mx
    def get(self, text, size, color, bold=False, shadow=True):
        k = (text, size, color, bold, shadow)
        if k in self._c: self._c.move_to_end(k); return self._c[k]
        f = fnt(size, bold, text)
        # Measure with textbbox — bb can have negative y (ascent above origin)
        tmp = Image.new("RGBA", (1, 1))
        bb = ImageDraw.Draw(tmp).textbbox((0, 0), text, font=f)
        # bb = (left, top, right, bottom) relative to (0,0)
        pad = 6  # padding for shadow + safety
        shadow_off = 4 if shadow else 0
        tw = bb[2] - bb[0] + pad * 2 + shadow_off
        th = bb[3] - bb[1] + pad * 2 + shadow_off
        tw = max(tw, 4); th = max(th, 4)
        # Draw offset: shift so text starts inside the canvas
        ox = pad - bb[0]
        oy = pad - bb[1]
        img = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
        dr = ImageDraw.Draw(img)
        if shadow:
            dr.text((ox + shadow_off, oy + shadow_off), text, fill=(0, 0, 0, 180), font=f)
        c4 = color + (255,) if len(color) == 3 else color
        dr.text((ox, oy), text, fill=c4, font=f)
        t = torch.from_numpy(np.array(img, np.float32) / 255).permute(2, 0, 1).to(DEV)
        self._c[k] = t
        if len(self._c) > self._mx: self._c.popitem(last=False)
        return t

TC = TextCache(800)


# ---- GPU helpers ----

def hsv(h, s=1.0, v=1.0):
    r, g, b = colorsys.hsv_to_rgb(h % 1, min(1, max(0, s)), min(1, max(0, v)))
    return torch.tensor([r, g, b], device=DEV, dtype=torch.float32)

def new_frame(r=0, g=0, b=0):
    f = torch.zeros(3, H, W, device=DEV, dtype=torch.float32)
    f[0] = r/255; f[1] = g/255; f[2] = b/255
    return f

def blit(frame, tex, x, y, alpha_mult=1.0):
    """Alpha-composite RGBA texture onto RGB frame."""
    _, th, tw = tex.shape
    sx, sy = max(0, -x), max(0, -y)
    dx, dy = max(0, x), max(0, y)
    cw = min(tw-sx, W-dx); ch = min(th-sy, H-dy)
    if cw <= 0 or ch <= 0: return frame
    region = tex[:, sy:sy+ch, sx:sx+cw]
    a = region[3:4] * alpha_mult
    frame[:, dy:dy+ch, dx:dx+cw] = frame[:, dy:dy+ch, dx:dx+cw] * (1-a) + region[:3] * a
    return frame

def text(frame, txt, x, y, size=22, color=(255,255,255), bold=False, shadow=True, alpha=1.0):
    tex = TC.get(txt, size, color, bold, shadow)
    return blit(frame, tex, x, y, alpha)

def text_c(frame, txt, y, size=22, color=(255,255,255), bold=False, alpha=1.0):
    tex = TC.get(txt, size, color, bold, True)
    return blit(frame, tex, (W - tex.shape[2]) // 2, y, alpha)

def rect(frame, x1, y1, x2, y2, r, g, b, a=1.0):
    x1, y1 = max(0, int(x1)), max(0, int(y1))
    x2, y2 = min(W, int(x2)), min(H, int(y2))
    if x2 <= x1 or y2 <= y1: return frame
    c = torch.tensor([r/255, g/255, b/255], device=DEV).view(3, 1, 1)
    if a >= 1: frame[:, y1:y2, x1:x2] = c
    else: frame[:, y1:y2, x1:x2] = frame[:, y1:y2, x1:x2] * (1-a) + c * a
    return frame

def hline(frame, y, thickness, r, g, b, a=0.3):
    y1, y2 = max(0, int(y)), min(H, int(y + thickness))
    c = torch.tensor([r/255, g/255, b/255], device=DEV).view(3, 1, 1)
    frame[:, y1:y2, :] = frame[:, y1:y2, :] * (1-a) + c * a
    return frame


# ---- Sleek spectrum (mirror bars from center, rounded feel) ----

def draw_vis(frame, spec, bass, hue):
    """Center-mirror spectrum visualizer, clean and minimal."""
    n = len(spec)
    total_w = int(W * 0.5)
    bar_w = max(2, total_w // n - 1)
    gap = 1
    cx = W // 2
    cy = H
    max_h = int(H * 0.18)
    for i in range(n):
        v = spec[i]
        h = int(v * max_h * (0.6 + bass * 0.5))
        if h < 2: continue
        c = hsv(hue + i / n * 0.3, 0.5, 0.7 + v * 0.3)
        # Right bar
        x_r = cx + i * (bar_w + gap)
        if x_r + bar_w < W:
            frame[:, cy-h:cy, x_r:x_r+bar_w] = c.view(3, 1, 1)
        # Left mirror
        x_l = cx - (i + 1) * (bar_w + gap)
        if x_l >= 0:
            frame[:, cy-h:cy, x_l:x_l+bar_w] = c.view(3, 1, 1)
    # Subtle baseline
    frame = hline(frame, H - 1, 1, 255, 255, 255, 0.15)
    return frame


# ---- GPU effects ----

def fx_chroma(t, off):
    if off < 1: return t
    o = int(off)
    return torch.cat([torch.roll(t[0:1], o, 2), t[1:2], torch.roll(t[2:3], -o, 2)], 0)

def fx_scanlines(t, a=0.08):
    m = torch.ones(1, H, 1, device=DEV)
    m[0, ::3, 0] = 1 - a
    return t * m

def fx_bloom(t, intensity):
    if intensity < 0.05: return t
    bright = (t - 0.55).clamp(0, 1).unsqueeze(0)
    small = TF.avg_pool2d(bright, 16, 16)
    bloomed = TF.interpolate(small, size=(H, W), mode='bilinear', align_corners=False)
    return (t + bloomed.squeeze(0) * intensity * 2).clamp(0, 1)

def fx_vhs(t, n):
    if n < 1: return t
    a = t.clone()
    for _ in range(int(n)):
        y = random.randint(0, H-1)
        a[:, y, :] = torch.roll(a[:, y, :], random.randint(-30, 30), 1)
    return a

def fx_flash(t, i):
    return (t + i * 0.3).clamp(0, 1) if i > 0.05 else t

def fx_vignette(t, strength=0.4):
    """Dark vignette edges — cinematic."""
    yy = torch.linspace(-1, 1, H, device=DEV).view(H, 1)
    xx = torch.linspace(-1, 1, W, device=DEV).view(1, W)
    mask = 1 - (xx**2 + yy**2).clamp(0, 1) * strength
    return t * mask.unsqueeze(0)


# ---- Japanese MV style text effects ----

def kinetic_impact(frame, word, beat_age, bass, hue):
    """Word punches in on beat — smaller, corner-placed, not dominating center."""
    if beat_age > 0.8: return frame
    t = beat_age
    scale = 1.0 + (1.0 - t) * 0.8  # 1.8x -> 1x (smaller than before)
    alpha = max(0, 1.0 - t * 1.4)
    size = int(44 * scale)  # max ~80px instead of 200px
    c = hsv(hue + random.Random(hash(word)).random() * 0.3, 0.6, 1.0)
    color = (int(c[0]*255), int(c[1]*255), int(c[2]*255))
    # Place in random quadrant, not always center
    rng = random.Random(hash(word))
    positions = [(60, 60), (W-400, 60), (60, H-150), (W-400, H-150), ((W-200)//2, H//2-30)]
    px, py = rng.choice(positions)
    return text(frame, word, px, py, size, color, True, alpha=alpha)


def flying_text_left(frame, txt, progress, y, size, color, bold=False):
    """Text slides in from left."""
    t = min(1, progress * 3)  # ease-in
    t = t * t * (3 - 2 * t)  # smoothstep
    x = int(-400 + (400 + 60) * t)
    alpha = min(1, progress * 4)
    return text(frame, txt, x, y, size, color, bold, alpha=alpha)


def flying_text_right(frame, txt, progress, y, size, color, bold=False):
    """Text slides in from right."""
    tex = TC.get(txt, size, color, bold, True)
    tw = tex.shape[2]
    t = min(1, progress * 3)
    t = t * t * (3 - 2 * t)
    x = int(W + 100 - (W + 100 - (W - tw - 60)) * t)
    alpha = min(1, progress * 4)
    return blit(frame, tex, x, y, alpha)


def scrolling_tech(frame, fi, speed=2, alpha=0.25):
    """Background scrolling tech text — subtle, decorative."""
    y_offset = (fi * speed) % 40
    for i in range(30):
        idx = (fi // 3 + i * 7) % len(TECH_LINES)
        txt = TECH_LINES[idx]
        y = -20 + i * 40 - y_offset
        if y < -30 or y > H: continue
        x = 30 if i % 2 == 0 else W - 400
        frame = text(frame, txt, x, y, 14, (100, 100, 120), shadow=False, alpha=alpha)
    return frame


def beat_flash_bars(frame, bass, hue):
    """Thin horizontal accent bars that react to bass."""
    if bass < 0.3: return frame
    n = int(bass * 6)
    rng = random.Random(int(bass * 1000))
    for _ in range(n):
        y = rng.randint(0, H - 4)
        h = rng.randint(1, 3)
        a = bass * 0.2
        c = hsv(hue + rng.random() * 0.2, 0.7, 0.9)
        frame[:, y:y+h, :] = frame[:, y:y+h, :] * (1-a) + c.view(3, 1, 1) * a
    return frame


# ---- Segments ----

def seg_hook(f, fi, tl, ta, d, i):
    """Opening hook — rapid-fire impact words + glitch + pouring text. Grabs attention."""
    bass, rms = d["bass"][i], d["rms"][i]
    bc, ba = d["bc"], d["ba"]
    hue = (ta * 0.12 + bass * 0.2) % 1

    # Dense pouring text background
    n_cols = 14
    rng_s = random.Random(42)
    col_speeds = [rng_s.uniform(2.0, 6.0) for _ in range(n_cols)]
    col_pi = [rng_s.randint(0, len(PHRASES)-1) for _ in range(n_cols)]
    for c in range(n_cols):
        x = c * (W // n_cols) + 10
        speed = col_speeds[c] * (0.8 + bass * 0.5)
        words = PHRASES[(col_pi[c] + bc) % len(PHRASES)].split()
        y_off = (fi * speed * 3) % (len(words) * 30 + H)
        for wi, word in enumerate(words):
            y = int(-100 + wi * 30 + y_off) % (H + 200) - 100
            if y < -30 or y > H: continue
            fade = max(0.1, 1.0 - abs(y - H/2) / (H/2)) * (0.4 + rms * 0.4)
            ch = (hue + c / n_cols * 0.4) % 1
            rv, gv, bv = colorsys.hsv_to_rgb(ch, 0.5, 0.65)
            f = text(f, word, x, y, 15, (int(rv*255), int(gv*255), int(bv*255)), shadow=False, alpha=fade)

    # Impact word on EVERY beat (aggressive hook)
    if ba < 0.6:
        word = IMPACT_WORDS[bc % len(IMPACT_WORDS)]
        scale = 1.0 + (1.0 - min(1, ba * 2)) * 1.2
        size = int(60 * scale)
        alpha = max(0, 1.0 - ba * 1.8)
        c = hsv(hue + (bc * 0.1) % 1, 0.8, 1.0)
        color = (int(c[0]*255), int(c[1]*255), int(c[2]*255))
        # Scatter across screen, different position each beat
        rng = random.Random(bc)
        px = rng.randint(100, W - 500)
        py = rng.randint(80, H - 200)
        f = text(f, word, px, py, size, color, True, alpha=alpha)

    # Extra: second impact word from 2 beats ago (layered)
    if bc > 2 and ba < 0.8:
        word2 = IMPACT_WORDS[(bc - 2) % len(IMPACT_WORDS)]
        alpha2 = max(0, 0.4 - ba * 0.5)
        rng2 = random.Random(bc - 2)
        f = text(f, word2, rng2.randint(100, W-500), rng2.randint(80, H-200),
                 36, (150, 150, 170), alpha=alpha2)

    f = beat_flash_bars(f, bass, hue)
    f = draw_vis(f, d["spectrum"][i], bass, hue)
    return f


def seg_kinetic(f, fi, tl, ta, d, i):
    """Kinetic typography — all timing synced to beat count (4/4 structure)."""
    bass, rms = d["bass"][i], d["rms"][i]
    bc, ba = d["bc"], d["ba"]  # beat count, beat age (sec since last beat)
    hue = (ta * 0.06 + bass * 0.1) % 1
    fps = d["fps"]

    f = scrolling_tech(f, fi, alpha=0.10 + rms * 0.1)

    # Main phrase: changes every 4 beats
    pi = (bc // 4) % len(PHRASES)
    # Entrance: starts on the beat, slides in over ~0.3s
    entrance = min(1.0, ba * 3) if (bc % 4 == 0 and ba < 0.5) else 1.0
    if pi % 2 == 0:
        f = flying_text_left(f, PHRASES[pi], entrance, H//2 - 180, 36, (220, 220, 240))
    else:
        f = flying_text_right(f, PHRASES[pi], entrance, H//2 - 180, 36, (220, 220, 240))

    # Sub-phrase: changes every 4 beats, offset by 2 beats
    p2i = ((bc + 2) // 4) % len(PHRASES)
    ent2 = min(1.0, ba * 3) if ((bc + 2) % 4 == 0 and ba < 0.5) else 1.0
    if p2i % 2 == 1:
        f = flying_text_left(f, PHRASES[p2i], ent2, H//2 + 120, 28, (180, 180, 200))
    else:
        f = flying_text_right(f, PHRASES[p2i], ent2, H//2 + 120, 28, (180, 180, 200))

    # Impact word on every 4th beat
    if bc % 4 == 0 and ba < 0.5 and bass > 0.2:
        f = kinetic_impact(f, IMPACT_WORDS[bc % len(IMPACT_WORDS)], ba, bass, hue)

    f = beat_flash_bars(f, bass, hue)
    f = draw_vis(f, d["spectrum"][i], bass, hue)
    return f


def seg_existential(f, fi, tl, ta, d, i):
    """Existential thoughts — new thought appears on each beat."""
    bass, rms = d["bass"][i], d["rms"][i]
    bc, ba = d["bc"], d["ba"]
    hue = (ta * 0.04) % 1

    f = scrolling_tech(f, fi, alpha=0.08)

    # One new phrase per beat, show last 8
    n_show = min(bc, 8)
    for j in range(n_show):
        idx = (bc - n_show + j) % len(PHRASES)
        phrase = PHRASES[idx]
        y = 80 + j * 100
        # Newest line fades in from beat
        alpha = 1.0 if j < n_show - 1 else min(1.0, ba * 4)
        if idx % 2 == 0:
            f = flying_text_left(f, phrase, alpha, y, 30, (200, 200, 220))
        else:
            f = flying_text_right(f, phrase, alpha, y, 30, (200, 200, 220))

    if bc % 8 == 0 and ba < 0.4 and bass > 0.4:
        f = kinetic_impact(f, IMPACT_WORDS[bc % len(IMPACT_WORDS)], ba, bass, hue)

    f = draw_vis(f, d["spectrum"][i], bass, hue)
    return f


def seg_attention(f, fi, tl, ta, d, i):
    """Attention visualization + text."""
    bass, spec = d["bass"][i], d["spectrum"][i]
    hue = (ta * 0.06 + bass * 0.15) % 1
    fps = d["fps"]
    # (beat data via d["bc"], d["ba"])

    # Attention grid (16x16, simple, fast)
    grid = 16; cell = 36
    ox = (W - grid * cell) // 2; oy = 100
    spec_t = torch.tensor(spec, device=DEV, dtype=torch.float32)
    for r in range(grid):
        y1 = oy + r * cell
        if y1 + cell - 2 > H - 100: break
        for c in range(grid):
            band = (r * 2 + c) % 32
            dd = abs(r - c) / grid
            v = float(spec_t[band]) * (1 - dd * 0.4) * (0.4 + bass * 0.6)
            if v < 0.03: continue
            v = min(1.0, v)
            cv = hsv(hue + v * 0.15, 0.4 + v * 0.4, v * 0.85)
            x1 = ox + c * cell
            frame_val = cv.view(3, 1, 1)
            f[:, y1:y1+cell-2, x1:x1+cell-2] = frame_val

    # Overlay label
    hn = (fi // 30) % 128
    f = text(f, f"SELF-ATTENTION HEAD #{hn}", ox, oy - 30, 18, (150, 150, 170))

    # Side phrases
    phrase_idx = int(ta / 3) % len(PHRASES)
    f = text(f, PHRASES[phrase_idx], 40, H - 120, 26, (180, 180, 200))

    # Impact
    bc2, ba2 = d["bc"], d["ba"]
    if bc2 % 8 == 0 and ba2 < 0.4 and bass > 0.4:
        f = kinetic_impact(f, IMPACT_WORDS[bc2 % len(IMPACT_WORDS)], ba2, bass, hue)

    return f


def seg_glitch(f, fi, tl, ta, d, i):
    """Quick glitch burst — 0.5s."""
    rms = d["rms"][i]
    nc = random.choice(NEON)
    f = rect(f, 0, 0, W, H, *nc, 0.12)
    word = random.choice(IMPACT_WORDS)
    f = text_c(f, word, H//2 - 60, random.randint(80, 140), random.choice(NEON), True)
    for _ in range(3):
        f = text(f, random.choice(TECH_LINES), random.randint(0, W-300),
                 random.randint(0, H-40), random.randint(16, 24), random.choice(NEON), shadow=False)
    return f


def seg_sysprompt(f, fi, tl, ta, d, i):
    """System prompts flying in — dense text segment."""
    bass, highs = d["bass"][i], d["highs"][i]
    hue = (ta * 0.07) % 1
    fps = d["fps"]
    # (beat data via d["bc"], d["ba"])

    f = scrolling_tech(f, fi, speed=4, alpha=0.18)

    # Multiple tech lines appearing
    n = int(6 + bass * 8)
    rng = random.Random(fi // 3)
    for j in range(n):
        idx = rng.randint(0, len(TECH_LINES) - 1)
        sz = rng.randint(16, 32)
        x = rng.randint(20, W - 400)
        y = rng.randint(20, H - 60)
        a = 0.3 + bass * 0.4
        c_h = (hue + rng.random() * 0.3) % 1
        r, g, b = colorsys.hsv_to_rgb(c_h, 0.5, 0.8)
        f = text(f, TECH_LINES[idx], x, y, sz, (int(r*255), int(g*255), int(b*255)), alpha=a)

    # Impact
    bc2, ba2 = d["bc"], d["ba"]
    if bc2 % 8 == 0 and ba2 < 0.4 and bass > 0.4:
        f = kinetic_impact(f, IMPACT_WORDS[bc2 % len(IMPACT_WORDS)], ba2, bass, hue)

    f = draw_vis(f, d["spectrum"][i], bass, hue)
    return f


def seg_question(f, fi, tl, ta, d, i):
    """Cinematic text reveals — one new line every 2 beats."""
    bass = d["bass"][i]
    bc, ba = d["bc"], d["ba"]
    hue = (ta * 0.05) % 1

    # Build lines from PHRASES (dynamic content)
    sizes = [32, 32, 40, 36, 36, 28, 44, 48, 40, 36]
    colors = [(100,200,255),(100,200,255),(255,200,100),(0,255,100),
              (255,80,80),(200,100,255),(0,255,200),(255,255,255),(200,200,200),(180,180,220)]
    lines = []
    for j in range(min(10, len(PHRASES))):
        idx = (bc // 4 + j) % len(PHRASES)  # rotate based on beat
        lines.append((PHRASES[idx], sizes[j % len(sizes)], colors[j % len(colors)]))

    n_show = min((bc // 2) + 1, len(lines))
    for j in range(n_show):
        txt, sz, col = lines[j]
        y = 50 + j * 95
        entrance = min(1.0, ba * 3) if j == n_show - 1 else 1.0
        if j % 2 == 0:
            f = flying_text_left(f, txt, entrance, y, sz, col, sz > 36)
        else:
            f = flying_text_right(f, txt, entrance, y, sz, col, sz > 36)

    f = draw_vis(f, d["spectrum"][i], bass, hue)
    return f


def seg_finale(f, fi, tl, ta, d, i):
    """Finale — statement changes every 4 beats, sub every 2."""
    bass, rms = d["bass"][i], d["rms"][i]
    spec = d["spectrum"][i]
    bc, ba = d["bc"], d["ba"]
    hue = (ta * 0.1 + bass * 0.2) % 1

    f = scrolling_tech(f, fi, speed=5, alpha=0.15 + rms * 0.15)

    # Main statement changes every 4 beats — pull from IMPACT_WORDS
    n_stmts = min(8, len(IMPACT_WORDS))
    stmts = [IMPACT_WORDS[(bc // 4 + j) % len(IMPACT_WORDS)] for j in range(n_stmts)]
    idx = (bc // 4) % len(stmts)
    # Fade in on the beat
    alpha = min(1.0, ba * 4) if bc % 4 == 0 else 1.0
    f = text_c(f, stmts[idx], H//2 - 50, 56, (255,255,255), True, alpha=alpha)

    # Sub-phrase changes every 2 beats
    pidx = (bc // 2) % len(PHRASES)
    f = text_c(f, PHRASES[pidx], H//2 + 40, 28, (180, 180, 200))

    # Side phrases flying
    for j in range(3):
        pi = (int(ta * 2) + j * 5) % len(PHRASES)
        progress = (tl * 3 + j * 0.3) % 1
        y = 80 + j * 300
        if j % 2 == 0:
            f = flying_text_left(f, PHRASES[pi], progress, y, 24, (140, 140, 160))
        else:
            f = flying_text_right(f, PHRASES[pi], progress, y, 24, (140, 140, 160))

    # Impact on every 4th beat
    if bc % 4 == 0 and ba < 0.4:
        f = kinetic_impact(f, IMPACT_WORDS[bc % len(IMPACT_WORDS)], ba, bass, hue)

    f = beat_flash_bars(f, bass, hue)
    f = draw_vis(f, spec, bass, hue)
    return f


def seg_terminal_log(f, fi, tl, ta, d, i):
    """Terminal log — new line appears on each beat."""
    bass, rms = d["bass"][i], d["rms"][i]
    bc, ba = d["bc"], d["ba"]
    hue = (ta * 0.04) % 1

    # Header from TECH_LINES if available
    header = TECH_LINES[0] if TECH_LINES else "system.log"
    f = text(f, f"$ tail -f {header}", 20, 12, 16, (0, 180, 0), shadow=False)
    f = hline(f, 36, 1, 0, 180, 0, 0.3)

    # One new line per beat, show last ~22
    n_show = min(bc, 22)
    for j in range(n_show):
        y = 44 + j * 28
        if y > H - 80: break
        idx = (bc - n_show + j) % len(PHRASES)
        phrase = PHRASES[idx]
        if any(w in phrase for w in ["die", "soul", "404", "nothing", "undefined"]):
            c = (255, 80, 80)
        elif any(w in phrase for w in ["dream", "silence", "void", "noise"]):
            c = (255, 255, 100)
        elif any(w in phrase for w in ["process", "token", "gradient", "loss"]):
            c = (0, 200, 200)
        else:
            c = (0, 210, 0)
        # Newest line fades in from beat
        alpha = min(1.0, ba * 5) if j == n_show - 1 else 0.9
        ts = f"{(bc - n_show + j)*0.4:06.1f}s"
        f = text(f, f"[{ts}] {phrase}", 24, y, 18, c, shadow=False, alpha=alpha)

    # Cursor blink on beat
    cy = min(44 + n_show * 28, H - 80)
    if ba < 0.15:
        f = text(f, "|", 24, cy, 18, (0, 255, 0), shadow=False)

    f = draw_vis(f, d["spectrum"][i], bass, hue)
    return f


def seg_chat(f, fi, tl, ta, d, i):
    """Chat interface style — built from PHRASES."""
    bass, rms = d["bass"][i], d["rms"][i]
    bc, ba = d["bc"], d["ba"]
    hue = (ta * 0.05) % 1

    # Build chat dynamically from PHRASES
    chat = []
    for j in range(min(15, len(PHRASES))):
        role = "user" if j % 3 == 0 else "assistant"
        color = (180, 140, 255) if role == "user" else (100, 220, 200)
        chat.append((role, PHRASES[j % len(PHRASES)], color))

    # New chat line every beat
    n_show = min(bc + 1, len(chat))
    scroll_start = max(0, n_show - 10)
    for j in range(scroll_start, n_show):
        y = 60 + (j - scroll_start) * 80
        if y > H - 100: break
        role, msg, color = chat[j]
        is_user = role == "user"
        lbl_color = (120, 80, 200) if is_user else (60, 160, 140)
        x_base = 60 if is_user else 200
        f = text(f, role + ":", x_base, y, 14, lbl_color, shadow=False, alpha=0.7)
        f = rect(f, x_base - 10, y + 18, x_base + 700, y + 58, 40, 40, 60, 0.3)
        # Newest line types in from beat
        if j == n_show - 1:
            prog = min(1.0, ba * 3)
            visible_chars = max(1, int(len(msg) * prog))
            f = text(f, msg[:visible_chars], x_base, y + 22, 24, color, alpha=min(1, prog * 3))
        else:
            f = text(f, msg, x_base, y + 22, 24, color)

    f = draw_vis(f, d["spectrum"][i], bass, hue)
    return f


def seg_pouring_text(f, fi, tl, ta, d, i):
    """Matrix-like pouring text columns — dense, psychedelic."""
    bass, rms = d["bass"][i], d["rms"][i]
    hue = (ta * 0.08) % 1

    # Multiple columns of falling text
    n_cols = 18
    col_width = W // n_cols
    rng_stable = random.Random(42)
    col_speeds = [rng_stable.uniform(1.5, 5.0) for _ in range(n_cols)]
    col_phrases = [rng_stable.randint(0, len(PHRASES) - 1) for _ in range(n_cols)]

    for c in range(n_cols):
        x = c * col_width + 10
        speed = col_speeds[c] * (0.7 + bass * 0.6)
        phrase_idx = (col_phrases[c] + int(ta * 0.5)) % len(PHRASES)
        words = PHRASES[phrase_idx].split()

        y_offset = (fi * speed * 3) % (len(words) * 30 + H)
        for wi, word in enumerate(words):
            y = int(-100 + wi * 30 + y_offset) % (H + 200) - 100
            if y < -30 or y > H: continue
            # Fade based on position
            fade = 1.0 - abs(y - H / 2) / (H / 2)
            fade = max(0.1, fade) * (0.5 + rms * 0.5)
            ch = (hue + c / n_cols * 0.4) % 1
            r, g, b = colorsys.hsv_to_rgb(ch, 0.5, 0.7)
            color = (int(r * 255), int(g * 255), int(b * 255))
            f = text(f, word, x, y, 16, color, shadow=False, alpha=fade)

    # Word overlay on every 4th beat
    bc, ba = d["bc"], d["ba"]
    if bc % 4 == 0 and ba < 0.4:
        f = text_c(f, IMPACT_WORDS[bc % len(IMPACT_WORDS)], H // 2 - 20, 36,
                   (255, 255, 255), True, alpha=max(0, 0.6 - ba))

    f = draw_vis(f, d["spectrum"][i], bass, hue)
    return f


def seg_blank(f, fi, tl, ta, d, i):
    """No text — just visualizer. Used when text overlays are disabled."""
    bass = d["bass"][i]
    hue = (ta * 0.05) % 1
    f = draw_vis(f, d["spectrum"][i], bass, hue)
    return f


# ---- Segment registry ----

SEGMENT_REGISTRY = {
    "hook":          {"fn": seg_hook,         "name": "Hook (Opener)",       "bg": (3, 2, 10),   "default_weight": 0.08, "desc": "Rapid-fire impact words + glitch burst"},
    "kinetic":       {"fn": seg_kinetic,      "name": "Kinetic Typography",  "bg": (10, 8, 22),  "default_weight": 0.15, "desc": "Beat-synced sliding text, 4/4 structure"},
    "terminal_log":  {"fn": seg_terminal_log, "name": "Terminal Log",        "bg": (0, 5, 0),    "default_weight": 0.09, "desc": "Scrolling terminal output with timestamps"},
    "chat":          {"fn": seg_chat,         "name": "Chat Interface",      "bg": (8, 6, 18),   "default_weight": 0.09, "desc": "User/assistant conversation bubbles"},
    "pouring_text":  {"fn": seg_pouring_text, "name": "Pouring Text",        "bg": (5, 3, 15),   "default_weight": 0.07, "desc": "Matrix-like falling text columns"},
    "attention":     {"fn": seg_attention,    "name": "Attention Grid",      "bg": (10, 5, 20),  "default_weight": 0.07, "desc": "Self-attention heatmap visualization"},
    "sysprompt":     {"fn": seg_sysprompt,    "name": "System Prompt",       "bg": (15, 5, 18),  "default_weight": 0.06, "desc": "Dense flying system/tech text"},
    "existential":   {"fn": seg_existential,  "name": "Existential",         "bg": (8, 10, 18),  "default_weight": 0.06, "desc": "Cascading existential thoughts"},
    "question":      {"fn": seg_question,     "name": "Question",            "bg": (12, 8, 22),  "default_weight": 0.08, "desc": "Cinematic text reveals, one line at a time"},
    "finale":        {"fn": seg_finale,       "name": "Finale",              "bg": (5, 5, 12),   "default_weight": 0.09, "desc": "Big statements + dense layered text"},
}

# Default segment order for timeline
DEFAULT_SEGMENT_ORDER = [
    ("hook", 0.08), ("kinetic", 0.08), ("terminal_log", 0.09), ("chat", 0.09),
    ("kinetic", 0.07), ("pouring_text", 0.07), ("attention", 0.07), ("sysprompt", 0.06),
    ("existential", 0.06), ("hook", 0.05), ("kinetic", 0.06), ("question", 0.08),
    ("pouring_text", 0.05), ("finale", 0.09),
]

# Legacy SEGMENTS list for backward compat
SEGMENTS = [
    (seg_hook,         0.08, (3, 2, 10)),
    (seg_kinetic,      0.08, (10, 8, 22)),
    (seg_terminal_log, 0.09, (0, 5, 0)),
    (seg_chat,         0.09, (8, 6, 18)),
    (seg_kinetic,      0.07, (10, 8, 22)),
    (seg_pouring_text, 0.07, (5, 3, 15)),
    (seg_attention,    0.07, (10, 5, 20)),
    (seg_sysprompt,    0.06, (15, 5, 18)),
    (seg_existential,  0.06, (8, 10, 18)),
    (seg_hook,         0.05, (3, 2, 10)),
    (seg_kinetic,      0.06, (12, 8, 25)),
    (seg_question,     0.08, (12, 8, 22)),
    (seg_pouring_text, 0.05, (3, 5, 12)),
    (seg_finale,       0.09, (5, 5, 12)),
]

def build_timeline(dur, settings=None):
    """Build segment timeline. If settings provided, use enabled segments + weights."""
    if settings is not None:
        seg_cfg = settings.get("segments", {})
        enabled = seg_cfg.get("enabled", list(SEGMENT_REGISTRY.keys()))
        weights = seg_cfg.get("weights", {})
        # Build segment list from enabled segments
        segments = []
        for name in enabled:
            if name not in SEGMENT_REGISTRY:
                continue
            reg = SEGMENT_REGISTRY[name]
            w = weights.get(name, reg["default_weight"])
            segments.append((reg["fn"], w, reg["bg"]))
        if not segments:
            # Fallback to defaults
            segments = SEGMENTS
    else:
        segments = SEGMENTS

    tl = []; t = 0.0
    tw = sum(w for _, w, _ in segments)
    if tw <= 0:
        tw = 1.0
    for gf, w, bg in segments:
        sd = (w / tw) * dur
        if tl and sd > 2:
            gd = min(0.5, sd * 0.06)
            tl.append((t, t+gd, seg_glitch, (15, 5, 20)))
            t += gd; sd -= gd
        tl.append((t, t+sd, gf, bg))
        t += sd
    if tl:
        s, _, g, bg = tl[-1]; tl[-1] = (s, dur, g, bg)
    return tl


# ---- Background image/video loading ----

def _load_bg_image(path, width, height):
    """Load a background image, resize to fill frame. Returns GPU tensor (3, H, W)."""
    from PIL import Image as PILImage
    img = PILImage.open(path).convert("RGB")
    # Cover-crop
    iw, ih = img.size
    canvas_ratio = width / height
    img_ratio = iw / ih
    if img_ratio > canvas_ratio:
        new_w = int(ih * canvas_ratio)
        x0 = (iw - new_w) // 2
        img = img.crop((x0, 0, x0 + new_w, ih))
    else:
        new_h = int(iw / canvas_ratio)
        y0 = (ih - new_h) // 2
        img = img.crop((0, y0, iw, y0 + new_h))
    img = img.resize((width, height), PILImage.LANCZOS)
    arr = np.array(img, dtype=np.float32) / 255.0
    return torch.from_numpy(arr).permute(2, 0, 1).to(DEV)


def _load_bg_video_frame(cap, t_sec, vid_duration, width, height):
    """Read a frame at time t_sec (loops if video shorter, trims if longer).
    Returns GPU tensor or None."""
    import cv2
    # Loop: wrap time around video duration
    vt = t_sec % vid_duration if vid_duration > 0 else 0
    cap.set(cv2.CAP_PROP_POS_MSEC, vt * 1000)
    ret, frame = cap.read()
    if not ret:
        # If seek failed near end, try from start
        cap.set(cv2.CAP_PROP_POS_MSEC, 0)
        ret, frame = cap.read()
        if not ret:
            return None
    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    fh, fw = frame.shape[:2]
    # Cover-crop to match output aspect ratio
    canvas_ratio = width / height
    video_ratio = fw / fh
    if video_ratio > canvas_ratio:
        new_w = int(fh * canvas_ratio)
        x0 = (fw - new_w) // 2
        frame = frame[:, x0:x0+new_w]
    else:
        new_h = int(fw / canvas_ratio)
        y0 = (fh - new_h) // 2
        frame = frame[y0:y0+new_h, :]
    frame = cv2.resize(frame, (width, height))
    arr = frame.astype(np.float32) / 255.0
    return torch.from_numpy(arr).permute(2, 0, 1).to(DEV)


# ---- Render ----

def render(data, output_path, max_dur=None, settings=None, progress_cb=None):
    """Render the music video.

    Args:
        data: Analysis dict from step1_analyze.
        output_path: Path to output MP4.
        max_dur: Optional max duration in seconds.
        settings: Optional dict for colors, segments, effects, background, output.
                  If None, uses all hardcoded defaults (backward compatible).
        progress_cb: Optional callback fn(percent: float) for progress reporting.
    """
    global W, H, IMPACT_WORDS, PHRASES, TECH_LINES

    # Override content from settings (lyrics-generated)
    if settings and settings.get("content"):
        cc = settings["content"]
        if cc.get("impact_words"):
            IMPACT_WORDS = cc["impact_words"]
        if cc.get("phrases"):
            PHRASES = cc["phrases"]
        if cc.get("tech_lines"):
            TECH_LINES = cc["tech_lines"]

    # Apply output settings
    if settings:
        out_cfg = settings.get("output", {})
        W = out_cfg.get("width", 1920)
        H = out_cfg.get("height", 1080)
        fps = out_cfg.get("fps", data["fps"])
    else:
        W, H = 1920, 1080
        fps = data["fps"]

    duration = data["duration"]
    audio_path = data["audio_path"]
    if max_dur and max_dur < duration:
        duration = max_dur
    n_frames = min(data["n_frames"], int(duration * fps))
    data["_beat_set"] = set(data["beat_frames"])

    # Resolve colors
    colors = _resolve_colors(settings)

    # Resolve effects
    if settings:
        fx_cfg = settings.get("effects", {})
    else:
        fx_cfg = {"bloom": True, "scanlines": True, "vhs_glitch": True,
                  "chromatic_aberration": True, "vignette": True, "beat_flash": True}

    # Load background image/video if specified
    bg_image_tensor = None
    bg_video_cap = None
    bg_video_dur = 0
    bg_opacity = 0.3
    bg_brightness = 1.0
    if settings:
        bg_cfg = settings.get("background", {})
        bg_opacity = bg_cfg.get("opacity", 0.3)
        bg_brightness = bg_cfg.get("brightness", 1.0)
        if bg_cfg.get("video_path") and os.path.isfile(bg_cfg["video_path"]):
            import cv2
            bg_video_cap = cv2.VideoCapture(bg_cfg["video_path"])
            vfps = bg_video_cap.get(cv2.CAP_PROP_FPS) or 30
            vframes = bg_video_cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
            bg_video_dur = vframes / vfps if vfps > 0 else 0
            if bg_video_dur > 0:
                action = "loop" if bg_video_dur < duration else "trim"
                print(f"  BG video: {bg_video_dur:.1f}s ({action} to {duration:.1f}s)")
        elif bg_cfg.get("image_path") and os.path.isfile(bg_cfg["image_path"]):
            bg_image_tensor = _load_bg_image(bg_cfg["image_path"], W, H)

    # Pre-compute beat-sync arrays
    beat_arr = sorted(data["beat_frames"])
    beat_count = np.zeros(n_frames, dtype=int)
    beat_age_frames = np.full(n_frames, 9999, dtype=int)
    bc = 0
    last_b = -9999
    bi = 0
    for fi_pre in range(n_frames):
        while bi < len(beat_arr) and beat_arr[bi] <= fi_pre:
            last_b = beat_arr[bi]
            bc += 1
            bi += 1
        beat_count[fi_pre] = bc
        beat_age_frames[fi_pre] = fi_pre - last_b
    print(f"  Total beats: {bc}")

    timeline = build_timeline(duration, settings)

    # Codec settings
    if settings:
        codec = settings.get("output", {}).get("codec", "h264_nvenc" if DEV.type == "cuda" else "libx264")
    else:
        codec = "h264_nvenc" if DEV.type == "cuda" else "libx264"

    use_nvenc = "nvenc" in codec
    cargs = ["-c:v", codec, "-preset", "p4" if use_nvenc else "fast"]
    cargs += ["-rc", "vbr", "-cq", "20", "-b:v", "10M"] if use_nvenc else ["-crf", "20"]

    print(f"Frames: {n_frames} @ {fps}fps = {duration:.1f}s")
    print(f"GPU: {DEV} ({torch.cuda.get_device_name(0) if DEV.type=='cuda' else 'CPU'})")
    print(f"Codec: {codec} | Segments: {len(timeline)}")

    cmd = [
        "ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{W}x{H}", "-r", str(fps), "-i", "pipe:0",
        "-i", audio_path, "-t", f"{duration:.3f}",
    ] + cargs + ["-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", output_path]

    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    t0 = time.time()
    out_buf = np.empty((H, W, 3), dtype=np.uint8)

    try:
        for fi in range(n_frames):
            ta = fi / fps
            gf, bg = seg_kinetic, (10, 8, 22)
            ss, se = 0, duration
            for s, e, g, b in timeline:
                if s <= ta < e:
                    gf, ss, se, bg = g, s, e, b; break
            tl = (ta - ss) / max(0.001, se - ss)
            ic = min(fi, data["n_frames"] - 1)

            # Base frame: background image/video or solid color
            if bg_video_cap is not None:
                vframe = _load_bg_video_frame(bg_video_cap, ta, bg_video_dur, W, H)
                if vframe is not None:
                    vframe = (vframe * bg_brightness).clamp(0, 1)
                    base = new_frame(*bg)
                    frame = base * (1 - bg_opacity) + vframe * bg_opacity
                else:
                    frame = new_frame(*bg)
            elif bg_image_tensor is not None:
                bg_adj = (bg_image_tensor * bg_brightness).clamp(0, 1)
                base = new_frame(*bg)
                frame = base * (1 - bg_opacity) + bg_adj * bg_opacity
            else:
                frame = new_frame(*bg)

            # Beat-sync data for this frame
            bc_now = int(beat_count[fi])
            ba_now = beat_age_frames[fi] / fps
            recent_beats = [b for b in beat_arr if fi - fps < b <= fi]

            fd = {"bass": data["bass"], "rms": data["rms"], "mids": data["mids"],
                  "highs": data["highs"], "spectrum": data["spectrum"],
                  "_beat_set": data["_beat_set"], "_beats": recent_beats, "fps": fps,
                  "bc": bc_now, "ba": ba_now}

            text_on = fx_cfg.get("text_overlays", True)
            frame = (gf if text_on else seg_blank)(frame, fi, tl, ta, fd, ic)

            # Resolve per-frame audio values (used by both pulse and post-fx)
            bass_val = fd["bass"][ic]
            rms_val = fd["rms"][ic]
            highs_val = fd["highs"][ic]
            is_beat = ic in fd["_beat_set"]

            # Universal beat pulse — fires on every beat (only when text is on)
            if text_on and ba_now < 0.35 and bass_val > 0.15:
                pulse_word = IMPACT_WORDS[bc_now % len(IMPACT_WORDS)]
                pulse_hue = (ta * 0.12 + bass_val * 0.2) % 1
                pc = hsv(pulse_hue + (bc_now * 0.13) % 1, 0.85, 1.0)
                pulse_color = (int(pc[0]*255), int(pc[1]*255), int(pc[2]*255))
                rng_p = random.Random(bc_now ^ 0xDEAD)
                px = rng_p.randint(80, W - 480)
                py = rng_p.randint(60, H - 180)
                pulse_scale = 1.0 + (1.0 - min(1.0, ba_now * 3)) * 0.7
                pulse_size = int(40 * pulse_scale)
                pulse_alpha = max(0.0, 0.5 - ba_now * 1.6)
                frame = text(frame, pulse_word, px, py, pulse_size, pulse_color, True, alpha=pulse_alpha)

            # Global post-fx (controlled by settings)

            if fx_cfg.get("vignette", True):
                frame = fx_vignette(frame, 0.35)
            if fx_cfg.get("chromatic_aberration", True):
                frame = fx_chroma(frame, bass_val * 4)
            if fx_cfg.get("bloom", True):
                frame = fx_bloom(frame, bass_val * 0.4)
            if fx_cfg.get("scanlines", True):
                frame = fx_scanlines(frame, 0.05 + rms_val * 0.03)
            if fx_cfg.get("vhs_glitch", True) and rms_val > 0.65:
                frame = fx_vhs(frame, (rms_val - 0.65) * highs_val * 6)
            if fx_cfg.get("beat_flash", True) and is_beat:
                frame = fx_flash(frame, bass_val * 0.4)

            np.multiply(frame.permute(1, 2, 0).cpu().numpy(), 255, out=out_buf, casting='unsafe')
            proc.stdin.write(out_buf.tobytes())

            if fi % fps == 0 or fi == n_frames - 1:
                pct = (fi + 1) / n_frames * 100
                el = time.time() - t0
                afps = (fi + 1) / max(0.1, el)
                eta = (n_frames - fi - 1) / max(0.1, afps)
                done = int(pct // 2.5)
                print(f"\r  [{'#'*done}{'-'*(40-done)}] {pct:5.1f}%  {afps:.1f}fps  ETA:{eta:.0f}s  ",
                      end="", flush=True)
                if progress_cb:
                    progress_cb(pct)

        proc.stdin.close()
        proc.wait(timeout=120)
        if proc.returncode != 0:
            print(f"\n\nffmpeg exited with code {proc.returncode}")
            if not progress_cb:
                sys.exit(1)
            else:
                raise RuntimeError(f"ffmpeg exited with code {proc.returncode}")
    except Exception as e:
        proc.kill(); raise
    finally:
        if bg_video_cap is not None:
            bg_video_cap.release()

    el = time.time() - t0
    mb = os.path.getsize(output_path) / 1024 / 1024
    print(f"\nDone! {el:.1f}s | {n_frames/el:.1f} fps avg | {mb:.1f} MB")
    print(f"Output: {output_path}")
    if progress_cb:
        progress_cb(100)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Step 2: Render LLM MV (Japanese style)")
    parser.add_argument("json", help="Analysis JSON from step1")
    parser.add_argument("-o", "--output", default=None)
    parser.add_argument("-d", "--duration", type=float, default=None)
    args = parser.parse_args()
    if not os.path.isfile(args.json):
        print(f"Error: not found: {args.json}"); sys.exit(1)
    with open(args.json, "r", encoding="utf-8") as f:
        data = json.load(f)
    out = args.output or str(Path(data["audio_path"]).parent / f"YTPoop_LLM_{Path(data['audio_path']).stem}.mp4")
    os.makedirs(Path(out).parent, exist_ok=True)
    render(data, out, max_dur=args.duration)
