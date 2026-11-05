"""Reference style ("cinematic sermon clip") on top of an already-cut vertical video.

usage: python3 style_ref.py WORK STYLE.json OUT.mp4
  WORK needs: edit_1.3x.mp4 (cut video, no captions), _render/joined.mov (voice), words_final.json
  STYLE.json: {"title": ["JÁ SOMOS", "filhos de Deus!"], "title_until": 3.4,
               "quotes": [{"words": [194, 199], "lines": [[0, 3], [3, 6]], "bold": [3, 4, 5]}, ...],
               "handle": "@seuperfil" | null, "music": true, "music_db": -20}
Layers (bottom -> top): graded footage (blur-to-focus intro, vignette, grain) -> brush title -> person cut out
by MODNet (title sits BEHIND the speaker) -> small lowercase captions / typewriter quote cards -> handle.
"""
import json, os, re, subprocess, sys, wave
import numpy as np

work, style_p, out = sys.argv[1:4]
S = json.load(open(style_p))
Wd = json.load(open(f"{work}/words_final.json"))
tmp = f"{work}/_style"
os.makedirs(f"{tmp}/matte", exist_ok=True)
MODEL = os.environ.get("MODNET", os.path.join(os.path.dirname(work), "models", "modnet.onnx"))
W, H, FPS = 1080, 1920, 30


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(" ".join(cmd)[:400] + "\n" + r.stderr[-2500:])


dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                            f"{work}/edit_1.3x.mp4"], capture_output=True, text=True).stdout)


def ts(x):
    x = max(0.0, x)
    return f"{int(x // 3600)}:{int(x % 3600 // 60):02d}:{x % 60:05.2f}"


HEAD = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Poppins SemiBold,50,&H00FFFFFF,&H00FFFFFF,&H00000000,&H78000000,0,0,0,0,100,100,0,0,1,0,2,5,60,60,0,1
Style: Quote,Courier Prime,58,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,0,2,5,60,60,0,1
Style: Title,Permanent Marker,230,&H00CFE6F1,&H00CFE6F1,&H00000000,&H00000000,0,0,0,0,100,100,0,-4,1,0,0,5,20,20,0,1
Style: TitleSub,Permanent Marker,92,&H00CFE6F1,&H00CFE6F1,&H00000000,&H00000000,0,0,0,0,100,100,0,-4,1,0,0,5,20,20,0,1
Style: Handle,Poppins Medium,24,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,1,0,1,0,1,9,60,70,140,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

# ---------------- title (behind the speaker): letters typed one by one, each blurring in
tit, sub = S["title"]
t_end = S.get("title_until", 3.4)
ev = []
t0, step = 0.35, 0.11
for k in range(1, len(tit) + 1):
    a = t0 + (k - 1) * step
    shown = tit[:k - 1].replace(" ", "\\h")
    new = tit[k - 1].replace(" ", "\\h")
    rest = tit[k:].replace(" ", "\\h")
    b = t0 + k * step if k < len(tit) else t_end
    txt = (shown + r"{\blur10\alpha&H60&\t(0,160,\blur0\alpha&H00&)}" + new + r"{\alpha&HFF&}" + rest)
    fade = r"{\fad(0,280)}" if k == len(tit) else ""
    ev.append(f"Dialogue: 0,{ts(a)},{ts(b)},Title,,0,0,0,,{{\\pos(540,560)}}{fade}{txt}")
sa = t0 + len(tit) * step + 0.25
ev.append(f"Dialogue: 0,{ts(sa)},{ts(t_end)},TitleSub,,0,0,0,,{{\\pos(640,720)\\frz4\\fad(250,280)\\blur6\\t(0,250,\\blur0)}}{sub}")
open(f"{tmp}/title.ass", "w", encoding="utf-8").write(HEAD + "\n".join(ev) + "\n")

# ---------------- quotes: typewriter serif, keyword in BOLD CAPS, in quotation marks
fg, quote_spans = [], []
for q in S.get("quotes", []):
    i0, i1 = q["words"]
    ws = Wd[i0:i1 + 1]
    clean = lambda s: re.sub(r"[.,:;!?]+$", "", s)
    toks = []
    for j, w in enumerate(ws):
        t = clean(w["w"])
        if j in q.get("bold", []):
            t = t.upper()
        toks.append((t, j in q.get("bold", []), w["a"], max(w["b"], w["a"] + 0.12)))
    lines = q["lines"]
    end = ws[-1]["b"] + 0.9
    quote_spans.append((ws[0]["a"] - 0.05, end))
    # character reveal schedule: each word's letters spread across that word
    chars = []      # (time, line, token index, char index)
    for li, (a, b) in enumerate(lines):
        for ti in range(a, b):
            t, bold, ta, tb = toks[ti]
            for ci in range(len(t)):
                chars.append((ta + (tb - ta) * ci / max(1, len(t)), li, ti, ci))

    def render(n):
        shown = set((c[2], c[3]) for c in chars[:n])
        out_lines = []
        for li, (a, b) in enumerate(lines):
            parts = []
            for ti in range(a, b):
                t, bold, _, _ = toks[ti]
                vis = "".join(ch if (ti, ci) in shown else "" for ci, ch in enumerate(t))
                hid = "".join(ch for ci, ch in enumerate(t) if (ti, ci) not in shown)
                piece = (r"{\b1}" if bold else "") + vis + (r"{\alpha&HFF&}" + hid + r"{\alpha&H00&}" if hid else "") + (r"{\b0}" if bold else "")
                parts.append(piece)
            line = "\\h".join(parts)
            if li == 0:
                line = ('"' if n else r'{\alpha&HFF&}"{\alpha&H00&}') + line
            if li == len(lines) - 1:
                line = line + ('"' if n >= len(chars) else r'{\alpha&HFF&}"{\alpha&H00&}')
            sz = "" if li == 0 else r"{\fs50}"
            out_lines.append(sz + line)
        return "\\N".join(out_lines)

    times = [c[0] for c in chars] + [end]
    for n in range(1, len(chars) + 1):
        a, b = times[n - 1], times[n]
        if b - a < 0.005:
            continue
        fade = r"{\fad(0,180)}" if n == len(chars) else ""
        fg.append(f"Dialogue: 1,{ts(a)},{ts(b)},Quote,,0,0,0,,{{\\pos(540,1080)}}{fade}{render(n)}")

# ---------------- captions: small, lowercase, no punctuation, 2-3 words, centred (hidden under title/quotes)
busy = lambda a, b: a < t_end or any(a < qe and b > qs for qs, qe in quote_spans)
chunks, cur = [], []
for w in Wd:
    if cur:
        txt = " ".join(x["w"] for x in cur + [w])
        if len(cur) >= 3 or len(txt) > 18 or w["a"] - cur[-1]["b"] > 0.3 or cur[-1]["w"][-1] in ".?:!":
            chunks.append(cur)
            cur = []
    cur.append(w)
chunks.append(cur)
for n, ch in enumerate(chunks):
    a = ch[0]["a"]
    nxt = chunks[n + 1][0]["a"] if n + 1 < len(chunks) else ch[-1]["b"] + 0.5
    b = nxt if nxt - ch[-1]["b"] < 0.35 else ch[-1]["b"] + 0.15
    if busy(a, b):
        continue
    txt = " ".join(re.sub(r"[.,:;!?\"]", "", x["w"]) for x in ch)
    keep_cap = {"Deus", "João", "Ele"}
    txt = " ".join(t if t in keep_cap else t.lower() for t in txt.split())
    fg.append(f"Dialogue: 0,{ts(a)},{ts(b)},Cap,,0,0,0,,{{\\pos(540,1180)\\fad(60,0)}}{txt}")
if S.get("handle"):
    fg.append(f"Dialogue: 0,{ts(0)},{ts(dur - 1.0)},Handle,,0,0,0,,{S['handle'].upper()}")
open(f"{tmp}/fg.ass", "w", encoding="utf-8").write(HEAD + "\n".join(fg) + "\n")

# ---------------- base: grade + blur-to-focus intro + vignette + grain
grade = ("colorbalance=rs=-0.06:gs=0.01:bs=0.07:rm=0.02:bm=-0.02:rh=0.06:gh=0.02:bh=-0.05,"
         "curves=all='0/0.03 0.25/0.19 0.5/0.47 0.8/0.82 1/0.96',eq=saturation=0.82:contrast=1.06,"
         "vignette=angle=PI/4.2,noise=alls=7:allf=t")
run(["ffmpeg", "-v", "error", "-y", "-i", f"{work}/edit_1.3x.mp4", "-filter_complex",
     f"[0:v]{grade},split[s][b];[b]gblur=sigma=28,format=yuva420p,fade=t=out:st=0.15:d=0.75:alpha=1[bl];"
     f"[s][bl]overlay=eof_action=pass,format=yuv420p[v]",
     "-map", "[v]", "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "16", f"{tmp}/base.mp4"])

# ---------------- person matte for the title window (MODNet, Apache-2.0)
import onnxruntime as ort   # noqa: E402
from PIL import Image        # noqa: E402
sess = ort.InferenceSession(MODEL, providers=["CPUExecutionProvider"])
n_fr = int((t_end + 0.1) * FPS)
raw = subprocess.run(["ffmpeg", "-v", "error", "-i", f"{tmp}/base.mp4", "-frames:v", str(n_fr), "-vf", "scale=288:512",
                      "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
frames = np.frombuffer(raw, np.uint8).reshape(-1, 512, 288, 3)
prev = None
for k, fr in enumerate(frames):
    x = (fr.astype(np.float32) / 255 - 0.5) / 0.5
    m = sess.run(None, {"input": x.transpose(2, 0, 1)[None]})[0][0, 0]
    m = m if prev is None else 0.6 * m + 0.4 * prev          # light temporal smoothing against flicker
    prev = m
    Image.fromarray((np.clip(m, 0, 1) * 255).astype(np.uint8)).resize((W, H), Image.BILINEAR).save(f"{tmp}/matte/{k:04d}.png")

# ---------------- soft pad (synthesised, so there is no licence question): I-V-vi-IV in D, slow swells
voice_p = f"{tmp}/voice.wav"
run(["ffmpeg", "-v", "error", "-y", "-i", f"{work}/_render/joined.mov", "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
     "-ar", "48000", "-ac", "2", voice_p])
inputs_a, amix = ["-i", voice_p], "[0:a]anull[a]"
if S.get("music", True):
    sr = 48000
    n = int(dur * sr)
    t = np.arange(n) / sr
    chords = [[62, 66, 69, 74], [57, 61, 64, 69], [59, 62, 66, 71], [55, 59, 62, 67]]   # D A Bm G
    seg = 4.0
    y = np.zeros(n)
    for c in range(int(dur // seg) + 2):
        a0 = int(c * seg * sr)
        L = int((seg + 2.0) * sr)
        tt = np.arange(L) / sr
        env = np.minimum(1, tt / 1.6) * np.minimum(1, np.maximum(0, (seg + 2.0 - tt) / 2.0))
        tone = np.zeros(L)
        for note in chords[c % 4]:
            f = 440 * 2 ** ((note - 69) / 12)
            for det in (-0.12, 0.0, 0.12):                       # gentle chorus
                tone += np.sin(2 * np.pi * f * (1 + det / 100) * tt) + 0.25 * np.sin(4 * np.pi * f * tt)
        b = min(n, a0 + L) - a0
        if b > 0:
            y[a0:a0 + b] += (tone * env)[:b]
    y += 0.5 * np.sin(2 * np.pi * 36.71 * t) * (0.6 + 0.4 * np.sin(2 * np.pi * t / 16))  # soft low D
    y /= np.abs(y).max()
    with wave.open(f"{tmp}/pad.wav", "w") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sr)
        wf.writeframes((y * 0.8 * 32767).astype(np.int16).tobytes())
    inputs_a += ["-i", f"{tmp}/pad.wav"]
    amix = (f"[1:a]lowpass=f=2200,aecho=0.8:0.7:120|260:0.35|0.25,loudnorm=I={-14 + S.get('music_db', -20)},"
            f"afade=t=in:d=2.5,afade=t=out:st={dur - 2.5:.2f}:d=2.5,aformat=channel_layouts=stereo[m];"
            f"[0:a][m]amix=inputs=2:normalize=0,alimiter=limit=0.89[a]")

# ---------------- composite
fc = (f"color=c=black@0:s={W}x{H}:r={FPS}:d={dur:.3f},format=rgba,subtitles={tmp}/title.ass:alpha=1[ti];"
      f"[0:v][ti]overlay=format=auto[bt];"
      f"[1:v]format=gray,setpts=PTS-STARTPTS[mt];[0:v]trim=end_frame={n_fr},setpts=PTS-STARTPTS[pv];"
      f"[pv][mt]alphamerge[person];[bt][person]overlay=eof_action=pass,"
      f"subtitles={tmp}/fg.ass,fade=t=out:st={dur - 0.8:.2f}:d=0.8,format=yuv420p[v];"
      + amix.replace("[0:a]", f"[{2}:a]").replace("[1:a]", f"[{3}:a]"))
run(["ffmpeg", "-v", "error", "-y", "-i", f"{tmp}/base.mp4", "-framerate", str(FPS), "-i", f"{tmp}/matte/%04d.png"]
    + inputs_a + ["-filter_complex", fc, "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "medium",
                  "-crf", "20", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out])
print("->", out)
