---
name: sermon-cinematic-edit
description: Edit a vertical preaching/sermon clip in the cinematic Instagram-Reels style (brush title behind the speaker, typewriter quote cards, small lowercase captions, teal-warm film grade, soft music bed, punch-ins). Renders the finished MP4 locally with ffmpeg; no CapCut needed. Use when someone asks for a sermon/church clip edited "like the reference" or in this style.
---

# Cinematic sermon clip (vertical, 9:16)

Turns raw phone/camera footage of a preacher into a finished Reel in the style of the reference clip the viewer
supplied (`b3bea31895fc460c87670923152a5f59.mp4`, a 65 s clip from @advectaubate). It reuses the cut-list engine
of the `capcut-talking-head-edit` skill (`analyze.py`, `edl.py`, `qa.py`, `cct.py`) and renders straight to MP4.

## What the reference does (the style to copy)

Measured from the reference, second by second:

| Element | How it looks | How we build it |
|---|---|---|
| **Opening** | first 0.8 s goes from heavy blur to sharp | blurred copy fading out over the graded footage |
| **Hook title** | 1-2 big words in a cream brush/marker font (`SÓ DEUS`), typed letter by letter, each letter blurring in; a smaller script line under it (`faz isso!`); the text sits **behind the speaker's head** | `Permanent Marker` in ASS + person matte (MODNet) laid back on top |
| **Quote cards** | the key sentence in a typewriter serif, in quotation marks, keyword in **BOLD CAPS** (`"Enquanto DEUS / te esconde de uns..."`), typed in sync with the voice, mid-frame; captions hide while it shows | `Courier Prime`, character reveal timed to each word |
| **Captions** | small, white, lowercase, no punctuation, 2-3 words, centred just under the face, soft shadow, no highlight box | `Poppins SemiBold` 50 px on 1080 x 1920 |
| **Grade** | dark, teal shadows, warm skin, lowered saturation, crushed but soft blacks, vignette, fine grain | `colorbalance` + `curves` + `eq` + `vignette` + `noise` |
| **Pacing** | a new shot every 2-3 s; audience reaction b-roll (tears, raised hands) on emotional lines; several camera angles | punch-ins on every jump cut; **b-roll only if the viewer supplies it** |
| **Music** | a constant worship pad/instrumental bed, only 3-4 dB under the voice in pauses | synthesised pad (no licence issue) or the viewer's track, ~-20 LU under the voice |
| **Branding** | Instagram icon + handle small, top right; ends on an Instagram logo card over a blurred frame | `Handle` style; end card optional |
| **Ending** | last line lands, picture fades out | 0.8 s fade to black |

## Needs

- `ffmpeg` with libass, Python 3 with `numpy`, `Pillow`, `onnxruntime`, `faster-whisper`, `fonttools`, `brotli`.
- Network: Hugging Face (`huggingface.co`, `us.aws.cdn.hf.co`) for the Whisper model and MODNet; run Hugging Face
  downloads with `HF_HUB_DISABLE_XET=1`. Fonts come from npm (`@fontsource/*`), which is reachable as a package
  registry even when GitHub raw is not.
- Footage: the camera file, ideally ≤ 4K. Vertical phone video is auto-rotated by ffmpeg.

### One-time setup

```bash
pip install faster-whisper onnxruntime fonttools brotli --break-system-packages
# person matting model (Apache-2.0)
mkdir -p models && curl -sSL -o models/modnet.onnx https://huggingface.co/Xenova/modnet/resolve/main/onnx/model.onnx
# fonts: Permanent Marker (title), Courier Prime (quotes), Poppins (captions)
for p in permanent-marker courier-prime poppins; do npm pack -q @fontsource/$p; done
for t in fontsource-*.tgz; do mkdir -p x && tar -xzf $t -C x && mv x/package x/${t%.tgz}; done
python3 -c "
import glob,os; from fontTools.ttLib import TTFont
os.makedirs(os.path.expanduser('~/.fonts'),exist_ok=True)
for f in glob.glob('x/*/files/*-latin-*-normal.woff2'):
    t=TTFont(f); t.flavor=None; t.save(os.path.expanduser('~/.fonts/'+os.path.basename(f)[:-6]+'.ttf'))"
fc-cache -f
```

## Run order

| # | Step | Checkpoint with the viewer |
|---|---|---|
| 1 | Get the footage (Drive link must be "anyone with the link") and probe it | |
| 2 | Ask: speed (1.0x / 1.3x), title words, quote lines, handle, music yes/no | answers |
| 3 | `analyze.py` → `job.json` → `edl.py` → `qa.py` (from `capcut-talking-head-edit`) | |
| 4 | `render.py --sfx_db -99` → cut video `edit_1.3x.mp4` + voice `_render/joined.mov` | |
| 5 | `transcribe.py` (turbo) → fix words by hand → `map_words.py --speed S --text corrected.txt` | confirms doubtful words |
| 6 | Pick the title and 1-3 quote lines, write `style.json`, run `style_ref.py` | watches the result |
| 7 | Send a 720p preview (< 20 MB) and the full file with SendUserFile | |

Defaults when the viewer is quiet: 1.0x speed, title = the clip's central claim in 1-2 words, quote cards on the
theological punchline and on the last line, music on, no handle (ask for it: it is in the reference style).

## Rules

1. **Captions never sit on top of the title or a quote card.** `style_ref.py` hides them in those windows.
2. **Title behind the speaker only while the matte is good.** Check a still: hair/hands should cover the letters
   cleanly. If the speaker is small in frame or moves a lot, put the title in front instead (drop the matte).
3. **Keep the viewer's words.** Fix transcription errors by comparing at least two models; list the words you
   guessed from context in the report and ask.
4. **No sound effects unless asked.** This viewer found synthesised whooshes on zooms too loud; the reference has
   none on its punch-ins. If asked, keep them under −20 dB relative to the voice and use real recorded SFX.
5. **Music under the voice:** the pad is −20 LU under the voice by default; fade in 2.5 s, fade out 2.5 s.
6. **Never invent b-roll.** Audience-reaction shots are what make the reference feel big; ask for them (other
   camera angles, crowd shots) and insert them on emotional lines with `edl.py` inserts.
7. **Deliver under 30 MB as a preview,** plus the full-quality file.

## style.json

```json
{"title": ["JÁ SOMOS", "filhos de Deus!"], "title_until": 3.4,
 "quotes": [{"words": [194, 199], "lines": [[0, 3], [3, 6]], "bold": [3, 4, 5]},
            {"words": [237, 244], "lines": [[0, 3], [3, 8]], "bold": [2, 7]}],
 "handle": "@perfil", "music": true, "music_db": -20}
```
- `words`: first and last index in `words_final.json`; `lines`: token ranges inside the quote, one per line (the
  second line renders a little smaller, like the reference); `bold`: tokens shown in **BOLD CAPS**.

## Scripts (in `scripts/`)

- `render.py`: cut + punch-ins/push-ins + global speed (`--speed`), optional whooshes (`--sfx_db -99` disables).
- `transcribe.py`: Portuguese word timings with large-v3-turbo.
- `map_words.py`: words onto the final timeline, applying a hand-corrected transcript.
- `style_ref.py`: the reference look (grade, blur intro, brush title behind the speaker, typewriter quotes,
  lowercase captions, handle, music pad, fade out).

## Other skills worth installing (found online; review before running, they execute external code)

- **ffmpeg-skill** (MIT, `npx ffmpeg-skill`): 42 local FFmpeg tools — silence removal, reframing, karaoke captions,
  lower-thirds, LUTs, loudness, delivery checks. Good replacement for hand-written ffmpeg.
  https://github.com/kajisho5/ffmpeg-skill
- **Remotion agent skills** (`npx skills add remotion-dev/skills`): animated captions and kinetic typography in
  React; best for complex motion graphics. Check Remotion's company licence. https://www.remotion.dev/docs/ai/skills
- **Robust Video Matting** (GPL-3.0): higher quality person matte than MODNet when hair/hands matter.
- Free SFX sources if sound effects are wanted: Mixkit (Mixkit licence), Fiftysounds (free, no attribution).
