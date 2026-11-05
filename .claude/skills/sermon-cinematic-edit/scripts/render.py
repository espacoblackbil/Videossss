"""Render the edit straight to MP4 (no CapCut): camera clips with punch-ins/push-ins, global speed, soft whooshes.
usage: python3 render.py WORK SRC OUT [--speed 1.3] [--size 1080x1920] [--sfx_db -14]
"""
import json, os, subprocess, sys, wave
from concurrent.futures import ThreadPoolExecutor
import numpy as np

work, src, out = sys.argv[1:4]
arg = lambda k, d: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d
SPEED = float(arg("--speed", "1.3"))
OW, OH = (int(x) for x in arg("--size", "1080x1920").split("x"))
SFX_DB = float(arg("--sfx_db", "-14"))
E = json.load(open(f"{work}/edl.json"))
FPS = E["fps"]
tmp = f"{work}/_render"
os.makedirs(tmp, exist_ok=True)


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(" ".join(cmd) + "\n" + r.stderr[-2000:])


def clip(k, c):
    o = f"{tmp}/c{k:03d}.mp4"
    s0, s1 = c["scale0"], c["scale1"]
    n = c["src1"] - c["src0"]                       # frames at 30 fps, source time
    d = n / FPS
    sc = f"({s0}+({s1}-{s0})*min(1,t/{max(d - 1 / FPS, 1e-3):.4f}))"
    vf = (f"fps={FPS},scale=w='trunc({OW}*{sc}/2)*2':h='trunc({OH}*{sc}/2)*2':eval=frame:flags=bicubic,"
          f"crop={OW}:{OH},setpts=(PTS-STARTPTS)/{SPEED},fps={FPS},format=yuv420p")
    af = f"atrim=0:{d:.4f},apad,atrim=0:{d:.4f},asetpts=PTS-STARTPTS,atempo={SPEED}"
    run(["ffmpeg", "-v", "error", "-y", "-ss", f"{c['src0'] / FPS:.4f}", "-t", f"{d + 0.1:.4f}", "-i", src,
         "-vf", vf, "-af", af, "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-c:a", "pcm_s16le",
         "-ar", "48000", "-ac", "1", "-t", f"{d / SPEED:.4f}", f"{tmp}/c{k:03d}.mov"])
    return f"{tmp}/c{k:03d}.mov"


with ThreadPoolExecutor(2) as ex:
    parts = list(ex.map(lambda a: clip(*a), enumerate(E["clips"])))
open(f"{tmp}/list.txt", "w").write("".join(f"file '{p}'\n" for p in parts))
run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", f"{tmp}/list.txt", "-c", "copy", f"{tmp}/joined.mov"])

# ---- soft whoosh, synthesized (band-passed noise sweep with a smooth envelope)
sr, L = 48000, 0.42
t = np.arange(int(sr * L)) / sr
rng = np.random.default_rng(7)
noise = rng.normal(0, 1, t.size)
spec = np.fft.rfft(noise)
f = np.fft.rfftfreq(t.size, 1 / sr)
spec *= np.exp(-((np.log(f + 1) - np.log(1800)) ** 2) / 1.1)        # soft, airy band around 1.8 kHz
w = np.fft.irfft(spec, t.size)
env = np.sin(np.pi * np.clip(t / L, 0, 1)) ** 2.2
env *= np.exp(-((t - 0.24) / 0.12) ** 2) * 0.6 + 0.4
w = w * env
w /= np.abs(w).max()
pk = int(np.argmax(np.convolve(w ** 2, np.ones(480), "same")))     # sample where it peaks
wav_path = f"{tmp}/whoosh.wav"
with wave.open(wav_path, "w") as wf:
    wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sr)
    wf.writeframes((w * 0.9 * 32767).astype(np.int16).tobytes())

# moments: every push-in start, and every punch-in (framing jumps to a tighter scale on a cut)
hits, prev = [], None
for c in E["clips"]:
    t0 = c["tl0"] / FPS / SPEED
    if c.get("zoom") and (prev is None or prev.get("zoom") != c["zoom"]):
        hits.append(t0)
    elif prev is not None and not c["cont"] and c["scale0"] > prev["scale1"] + 0.03:
        hits.append(t0)
    prev = c
hits = [h for h in hits if h > 0.3]

# place whooshes into a mono track, level relative to the voice
raw = subprocess.run(["ffmpeg", "-v", "error", "-i", f"{tmp}/joined.mov", "-vn", "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"],
                     capture_output=True).stdout
voice = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
rms = lambda x: np.sqrt(np.mean(x ** 2) + 1e-12)
blk = voice[: len(voice) // 4800 * 4800].reshape(-1, 4800)
v_lvl = np.median(np.sqrt((blk ** 2).mean(1))[np.sqrt((blk ** 2).mean(1)) > rms(voice) * 0.5])
g = v_lvl * 10 ** (SFX_DB / 20) / rms(w[pk - 2400:pk + 2400])
fx = np.zeros_like(voice)
for h in hits:
    a = int(h * sr) - pk + int(0.03 * sr)       # whoosh peaks just as the zoom lands
    a0 = max(0, a)
    seg = w[a0 - a:][: len(fx) - a0] * g
    fx[a0:a0 + len(seg)] += seg
with wave.open(f"{tmp}/fx.wav", "w") as wf:
    wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sr)
    wf.writeframes((np.clip(fx, -1, 1) * 32767).astype(np.int16).tobytes())

run(["ffmpeg", "-v", "error", "-y", "-i", f"{tmp}/joined.mov", "-i", f"{tmp}/fx.wav",
     "-filter_complex", "[0:a][1:a]amix=inputs=2:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000,aformat=channel_layouts=stereo[a]",
     "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out])
print(f"{out}: {len(parts)} clips, {E['total_frames'] / FPS / SPEED:.1f}s at {SPEED}x, {len(hits)} whooshes at",
      [round(h, 2) for h in hits])
