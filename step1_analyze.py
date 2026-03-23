"""
Step 1: Audio -> JSON analysis data
====================================
Extracts beat, frequency bands, RMS, spectral flux per frame.
Output: a .json file that step2 uses to generate visuals.

Usage:
  python step1_analyze.py "D:\\download\\Metallic Rebellion.mp3"
  python step1_analyze.py "D:\\download\\Metallic Rebellion.mp3" -o analysis.json --fps 30
"""

import sys, os, json, tempfile, subprocess, argparse, time
from pathlib import Path
import numpy as np


def analyze(audio_path, fps=30):
    """Full audio analysis -> dict of per-frame data."""
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".raw")
    tmp.close()
    sr = 44100
    try:
        subprocess.run([
            "ffmpeg", "-y", "-i", audio_path,
            "-ar", str(sr), "-ac", "1", "-f", "s16le", "-acodec", "pcm_s16le",
            tmp.name
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        raw = np.fromfile(tmp.name, dtype=np.int16).astype(np.float32) / 32768.0
    finally:
        os.remove(tmp.name)

    duration = len(raw) / sr
    hop = sr // fps
    n_frames = len(raw) // hop

    rms = np.zeros(n_frames)
    bass = np.zeros(n_frames)       # 20-200 Hz
    mids = np.zeros(n_frames)       # 200-2000 Hz
    highs = np.zeros(n_frames)      # 2000-8000 Hz
    spectral_flux = np.zeros(n_frames)
    spectrum = np.zeros((n_frames, 32))

    window = np.hanning(hop).astype(np.float32)
    freq_bins = np.fft.rfftfreq(hop, 1.0 / sr)
    bass_mask = (freq_bins >= 20) & (freq_bins < 200)
    mid_mask = (freq_bins >= 200) & (freq_bins < 2000)
    high_mask = (freq_bins >= 2000) & (freq_bins < 8000)
    n_fft = hop // 2 + 1
    edges = np.clip(np.logspace(np.log10(1), np.log10(n_fft), 33).astype(int), 0, n_fft)

    prev_mag = None
    for i in range(n_frames):
        chunk = raw[i * hop:(i + 1) * hop]
        if len(chunk) < hop:
            chunk = np.pad(chunk, (0, hop - len(chunk)))
        rms[i] = np.sqrt(np.mean(chunk ** 2))
        fft_mag = np.abs(np.fft.rfft(chunk * window))
        bass[i] = np.mean(fft_mag[bass_mask]) if np.any(bass_mask) else 0
        mids[i] = np.mean(fft_mag[mid_mask]) if np.any(mid_mask) else 0
        highs[i] = np.mean(fft_mag[high_mask]) if np.any(high_mask) else 0
        if prev_mag is not None:
            spectral_flux[i] = np.sum(np.maximum(fft_mag - prev_mag, 0))
        prev_mag = fft_mag.copy()
        for b in range(32):
            lo, hi_b = edges[b], max(edges[b] + 1, edges[b + 1])
            spectrum[i, b] = np.mean(fft_mag[lo:hi_b])

    # Normalize each signal 0-1
    def norm(x):
        mx = np.max(x)
        return (x / mx).tolist() if mx > 0 else x.tolist()

    rms_n = norm(rms)
    bass_n = norm(bass)
    mids_n = norm(mids)
    highs_n = norm(highs)
    flux_n = norm(spectral_flux)
    spec_n = []
    for b in range(32):
        mx = np.max(spectrum[:, b])
        if mx > 0:
            spectrum[:, b] /= mx
    spec_n = spectrum.tolist()  # [n_frames][32]

    # Beat detection (onset via spectral flux peaks)
    flux_arr = np.array(flux_n)
    flux_smooth = np.convolve(flux_arr, np.ones(3) / 3, mode='same')
    half_sec = max(1, fps // 2)
    threshold = np.convolve(flux_arr, np.ones(half_sec) / half_sec, mode='same') * 1.5
    beat_frames = []
    last_beat = -fps
    for i in range(2, n_frames - 1):
        if flux_smooth[i] > threshold[i] and flux_smooth[i] > flux_smooth[i - 1]:
            if i - last_beat >= fps // 4:
                beat_frames.append(i)
                last_beat = i

    # Energy sections (low / mid / high energy zones)
    window_size = fps * 2  # 2-second window
    energy_level = []
    for i in range(n_frames):
        lo = max(0, i - window_size // 2)
        hi = min(n_frames, i + window_size // 2)
        avg = float(np.mean(rms[lo:hi]))
        energy_level.append(round(avg, 4))

    return {
        "audio_path": str(Path(audio_path).resolve()),
        "duration": round(duration, 3),
        "sample_rate": sr,
        "fps": fps,
        "n_frames": n_frames,
        "n_beats": len(beat_frames),
        "beat_frames": beat_frames,
        "rms": rms_n,
        "bass": bass_n,
        "mids": mids_n,
        "highs": highs_n,
        "spectral_flux": flux_n,
        "energy_level": energy_level,
        "spectrum": spec_n,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Step 1: Audio analysis -> JSON")
    parser.add_argument("audio", help="Path to audio file")
    parser.add_argument("-o", "--output", default=None, help="Output JSON path")
    parser.add_argument("--fps", type=int, default=30, help="Frames per second (default: 30)")
    args = parser.parse_args()

    if not os.path.isfile(args.audio):
        print(f"Error: not found: {args.audio}")
        sys.exit(1)

    out_json = args.output or str(
        Path(args.audio).with_suffix(".analysis.json")
    )

    print(f"Analyzing: {args.audio}")
    print(f"FPS: {args.fps}")
    t0 = time.time()

    result = analyze(args.audio, fps=args.fps)

    # Write JSON (compact floats)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)

    elapsed = time.time() - t0
    size_kb = os.path.getsize(out_json) / 1024
    print(f"Done in {elapsed:.1f}s")
    print(f"  Duration : {result['duration']:.1f}s")
    print(f"  Frames   : {result['n_frames']}")
    print(f"  Beats    : {result['n_beats']}")
    print(f"  Output   : {out_json} ({size_kb:.0f} KB)")
