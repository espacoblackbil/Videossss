---
name: capcut-talking-head-edit
description: Edit a talking-head video in CapCut by writing the project files directly, then add motion graphics. Use when someone asks Claude to edit their CapCut project.
---

# CapCut talking-head edit

Edits a talking-head video (camera footage plus screen recordings and screenshots) inside the viewer's own CapCut
project by writing its timeline files directly. It never uses computer use and never opens CapCut. Then it adds
motion graphics, either reused files or new ones built in Higgsfield's motion editor (Higgsedit).

What the viewer gets:
- cuts that remove repeats, false starts, resets and long pauses
- punch-ins on every jump cut and slow push-ins on the strong lines
- screen recordings and screenshots placed on the line that mentions them
- a grade layer and a music bed
- graphics on their own track with subtle UI sounds
- a low-res preview before anything is written

## Needs

- **The Claude desktop app, with this chat linked to the viewer's computer.** The device tools come from that link:
  `get_device_info`, `device_request_folder_access`, `device_bash`, `device_list_dir`, `device_stage_files` and
  `device_commit_files`. This was tested on a Mac with CapCut 9.5. On Windows the project folder is
  `%LOCALAPPDATA%\CapCut\User Data\Projects\com.lveditor.draft`, and the timeline file may be `draft_content.json`.
- **The international CapCut desktop app.** The timeline file must be plain JSON, meaning its first byte is `{`.
  JianYing encrypts its projects; if you find that, say so and stop.
- **In the workspace:** Python with `numpy` and `faster-whisper`, plus `ffmpeg`. Install with
  `pip install faster-whisper --break-system-packages`. The viewer's computer also has `ffmpeg` inside `device_bash`.
- **Only for new motion graphics:** the Higgsfield connector (`sandbox_exec`, `media_upload`, `media_confirm`).

## Run order

Make a task list from this table at the start, because the viewer may step away. Copy the scripts from the end of
this file into `work/scripts/`.

| # | Step | Checkpoint with the viewer |
|---|---|---|
| 0 | Access and folders | approves the folder prompts |
| 1 | Find the project, read the media bin, ask questions | answers 4 questions |
| 2 | Analysis: audio, transcript, loudness, contact sheets, proxies | |
| 3 | Cut list, then the read-back check (`qa.py`) until it's clean | |
| 4 | Templates, build, preview | watches the preview |
| 5 | Install | **confirms CapCut is quit** |
| 6 | Motion graphics: route A (reuse) or route B (Higgsfield) | route B: **approves the first graphic** |
| 7 | Install the graphics on top of the current project | **confirms CapCut is quit** |
| 8 | Report: what changed, what was left in, backups | |

If the viewer goes quiet, use the defaults: fit cutaways on a dark background, use the screenshots, tight pacing
with punch-ins, the full set of graphics, subtle sounds. Say which you used. Two things always wait for the
viewer: CapCut being quit before any write, and approval of the first new graphic.

## Hard rules

1. **Never write while CapCut is open.** It overwrites the timeline when it quits. Ask before every write, then
   write with `expectedMtimeMs` so the write is refused if anything changed since you staged.
2. **Re-read the project right before every write and keep the viewer's own edits.** `build.py` is only for an
   empty project. Everything after that, graphics included, goes through `overlays.py`, which builds on top of the
   current draft.
3. **No camera flash next to an overlay.** If a graphic or cutaway would start less than 0.5 s after a camera cut,
   it starts on the cut. If camera would show for less than 0.5 s after it before the next cut, it stretches to
   that cut (graphics may slow to 0.8x). If it can't stretch, it ends on the last cut inside it. Gaps of less than
   0.5 s between overlays are closed. `cct.snap_to_cuts` does this: `edl.py` calls it for cutaways and
   `overlays.py` for graphics. Invisible splits, meaning the same source continuing at the same framing, are not
   cuts.
4. **Clone every object from the viewer's own CapCut-saved projects** (`harvest.py`). Never invent fields, and
   never carry per-clip looks (LUTs, HSL, curves, masks) into a new edit.
5. **Keyframe `time_offset` is in source time:** the clip's source start plus the offset. The last keyframe sits
   one frame before the clip end.
6. **For a speed change,** the segment's `speed` and its `speeds` material hold the same value, and source
   duration = target duration x speed.
7. **Write all six timeline copies:** `draft_info.json`, `.bak` and `template-2.tmp`, both at the project root and
   in `Timelines/<main_timeline_id>/`. Set `tm_duration` in `draft_meta_info.json`.
8. **Media paths are the real paths on the viewer's computer,** never mount paths or workspace paths. Use CapCut's
   own media-bin durations as file lengths.
9. **Audio levels:** camera audio stays at 1.0; raise it only if its peaks allow. Screen recordings and graphics
   are muted. Music sits about 15 dB under the voice, sound effects about 6.5 dB under.
10. **The adjustment layer goes directly above the main track,** so cutaways and graphics keep their true colour.
11. **Find projects by `draft_name`** inside `draft_meta_info.json`. Folder names often differ.

## 0. Access

- Call `get_device_info`. Request every folder in one `device_request_folder_access` call, with a one-line reason:
  - `~/Movies`, which holds the CapCut projects at `~/Movies/CapCut/User Data/Projects/com.lveditor.draft`
  - the footage folder, which is wherever the media-bin paths point (external drives work: request the exact
    folder)
  - the music and sound effects folder. If the viewer only knows its name, ask for `~/Desktop` and `~/Documents`,
    then search with `find -maxdepth 4 -iname '*name*'`.
- Inside `device_bash`, connected folders appear at `$HOME/mnt/<folder name>`. Use a work folder of
  `<footage folder>/.claude_work/<project>/`, because the shell's home folder can't be staged. Deleting is blocked
  by default, so leave work files there and mention it at the end.
- Each `device_bash` call has 180 s. Never decode a 4K file end to end in one call: seek with `-ss` before `-i`,
  or split the work into chunks.

## 1. Find the project and ask

```bash
cd "$HOME/mnt/Movies/CapCut/User Data/Projects/com.lveditor.draft"
for d in */; do grep -q '"draft_name": *"<Name>"' "$d/draft_meta_info.json" 2>/dev/null && echo "$d"; done
head -c1 "<project>/draft_info.json"     # must print {
```
Read the media bin: `draft_meta_info.json` → `draft_materials[].value[]` → `file_Path`, `metetype`, `duration`
(microseconds), `width` and `height`. The longest video is usually the camera file.

Ask everything in one go with AskUserQuestion:
1. Which music folder and mood?
2. How should cutaways sit? Fit on a dark background (recommended), crop to fill, or picture-in-picture.
3. Use the screenshots too? (Recommended: yes.)
4. How tight should the pacing be? Tight with punch-ins (recommended), tight with no punch-ins, or natural.

## 2. Analysis

These run on the viewer's computer through `device_bash`; then stage the small results.
```bash
W="$HOME/mnt/<footage>/.claude_work/<project>"; mkdir -p "$W/frames"
ffmpeg -v error -y -i "<camera>" -vn -ac 1 -ar 16000 -c:a pcm_s16le "$W/camera_16k.wav"     # seconds, not minutes
ffmpeg -v error -y -i "<recording>.mov" -vf "fps=1/2,scale=480:-2,tile=4x4" -frames:v 1 "$W/frames/rec1.jpg"
for t in 5 60 120 180 240; do ffmpeg -v error -y -ss $t -i "<camera>" -frames:v 1 -vf scale=384:-2 "$W/frames/a_$t.jpg"; done
# preview proxies: 140 s chunks, 3 in parallel per call (about 45 s each for 4K)
for k in 0 1 2; do ffmpeg -v error -y -ss $((k*140)) -t 140 -i "<camera>" -vf scale=640:360 -r 30 -c:v libx264 -preset ultrafast -crf 32 -c:a aac -ac 1 "$W/proxy_$k.mp4" & done; wait
```
- Stage `camera_16k.wav` into `work/` and run `python3 scripts/analyze.py work`. It takes about 10 minutes for
  14 minutes of audio on 2 CPUs, so run it in the background.
- Stage the contact sheets and screenshots and look at them yourself, so you know what each one shows and which
  moment of a recording matters (a click, a sort, a hover).
- Stage the proxies and join them: `ffmpeg -f concat -safe 0 -i list.txt -c copy work/proxy_all.mp4`. Use 960 px
  proxies for the recordings, and 640x360 proxies for any graphics files later.

## 3. Cut list (`job.json` → `edl.py` → `qa.py`)

Read `work/phrases.txt` and fill in `job.json`; the format is in the `edl.py` docstring.
- **Repeats and false starts:** keep the last complete take and remove the earlier ones (`remove_words`). Remove a
  reset together with the silence after it. When a removal edge falls in continuous speech, use
  `force_start`/`force_end` at whisper's word boundary.
- **Push-ins (`zooms`), about one every 30 s:** the hook, each numbered point's title, teases ("but this next
  one…"), questions to the viewer, callbacks and the last line.
- **Cutaways (`inserts`):** anchor each one to the words that mention it. For a recording, pick `src` so the
  moment that matters lands while those words are said. A run of screenshots on one line is a `photo_seq`.
- Run `python3 scripts/edl.py work`. It prints removals, cutaways, push-ins and any snaps.
- **Then always run `python3 scripts/qa.py work` and read the whole `qa_transcript.txt`.** The first transcript
  merges repeats ("another example, another example"), so stumbles that are left only show up here. For each
  one, look at the loudness around it:
  `python3 -c "import numpy as n;d=n.load('work/db10ms.npy');print(''.join(' .:-=+*#%@'[min(9,max(0,int((v+70)/5)))] for v in d[S*100:E*100]))"`.
  Then add a `remove_time` entry whose edges sit in quiet stretches, re-run, and read it again. A
  self-correction with no silence to cut on stays in; list it in the report.
- **Music (`music.json`):** pick tracks by name from the mood folder, using `ffprobe` for durations. Use one track
  per section and switch at big turns (just before a point's title), overlapping 0.6 s each side with 1.2 s
  fades. On the last track, set `align` so a strong late hit lands on the final line. The video holds 2 s after
  the last word for the ring-out.

## 4. Templates, build, preview

- **Templates:** find the viewer's projects that already contain an adjustment layer, an audio clip and a video
  clip (`grep -l '"type":"adjust"' */draft_info.json`). Stage one to three of their `draft_info.json` files and run
  `python3 scripts/harvest.py work/templates.json <staged drafts>`. If it reports MISSING, ask the viewer to make a
  20-second template project once, then quit CapCut and harvest again:
  - import any video and put it on the timeline
  - add a music clip and give it a fade-in
  - add an adjustment layer and nudge its saturation
- **Plate:** a dark 1920x1080 PNG behind the cutaways. Make it in the workspace (radial gradient #1E2026 to
  #090A0C, plus about 1 level of noise), then commit it into the footage folder.
- **Build:** stage the empty project's `draft_info.json`, `draft_meta_info.json` and `Timelines/project.json` into
  `work/project/`, then run `python3 scripts/build.py work work/project work/build`.
- **Preview:** write `work/pathmap.json` mapping each real path in `work/build/device_paths.txt` to a local proxy
  or staged copy. Run `python3 scripts/preview.py work/build/draft_info.json work/pathmap.json work/preview.mp4`
  and send the preview with SendUserFile.

## 5 and 7. Install (both times)

1. Ask: "Is CapCut fully quit (Cmd+Q)?"
2. Run `device_list_dir` on the project. If the timeline file's `mtimeMs` changed since you staged it, stage it
   again, rebuild, and keep the viewer's edits.
3. Back up: `device_commit_files` the staged originals to `<project>/_backup_before_<step>_<YYYYMMDD-HHMM>/`.
4. Write the new timeline file to every path in `install_targets.txt` that exists, plus `draft_meta_info.json`.
   Pass `expectedMtimeMs` for the root timeline file and for the meta file.
5. Verify in `device_bash`: `md5sum` of all six copies must equal the build's md5. Every path in
   `device_paths.txt` must exist after mapping it to `$HOME/mnt/...`.
6. Tell the viewer to open CapCut and click the project.

## 6. Motion graphics

The graphics go on their own top track as full-frame, muted 4K30 H.264 clips. CapCut opens these without any
conversion. Each explainer gets a soft swipe as it cuts in, and each chapter card gets a swipe plus a soft ding,
from the viewer's sound effects (`sfx.json`).

**Route A: reuse existing graphics** (from an earlier edit of the same script, or files the viewer supplies)
1. Make contact sheets of each file, so you know what it shows and when its numbers land.
2. Write `graphics.json`: name, real path, duration, and a `start_phrase` taken from `words_tl.json`. Add an
   `end_phrase` when the graphic's beats should stretch to the viewer's pacing (0.8x to 1.25x).
3. Run `python3 scripts/place_graphics.py work`.
4. Stage the CURRENT project files into `work/current/` and run
   `python3 scripts/overlays.py work work/current work/build_mg`.
5. Preview with `preview.py`, check that the counters land on the words, then install as in step 7.

**Route B: build new graphics in Higgsfield (Higgsedit)**
1. **Design system.** If the viewer gives inspiration clips, make contact sheets and sample the background colour
   at corners and centre. The default house style is the kit below: warm near-black with a soft glow, dark cards
   with hairline borders, Inter, small letter-spaced labels and a coral accent.
2. **Plan every graphic against `words_tl.json`.** Include a chapter card for each numbered point, then stats and
   counters, comparisons, processes, comments or quotes, callbacks and an end checklist. That comes to about one
   every 25 s. A graphic replaces any screenshot cutaway it covers; put the thumbnail inside the card.
3. **Build the first one** in the sandbox, check stills, render at 4K, and send both the 4K file and an
   in-context clip (the preview with the graphic overlaid). Ask with AskUserQuestion:
   - approve, approve with tweaks, or change the direction
   - accent colour
   - density: about 28, about 15, or explainers only
   - subtle UI sounds: yes or no
4. Once approved, build the rest with the same kit. Each graphic is designed for its exact slot, so
   `graphics.json` carries `a`/`b` seconds. Download the renders, commit them into
   `<footage folder>/Motion Graphics (Claude)/` (30 MB per file, 100 MB per call), then run `overlays.py` and
   install.

**Higgsedit workflow** (load `get_workflow_instructions` with `video-editing` once for the API)
- The sandbox has the `higgsedit` CLI with 1 CPU; pass `size: "xl"` for 4K renders. Design everything in
  1920x1080 units through `u()`. Use `S = 0.5` for quick stills and `S = 2` for 3840x2160 finals.
- **Getting assets in** (thumbnails, the background): make them in the workspace, call `media_upload` (filename),
  `curl -X PUT` from the workspace, call `media_confirm`, then `curl -sf -o assets/x.png <url>` in the sandbox.
- **Rendering and getting files out:** call `media_upload` for the output filename first. Then, in ONE
  `sandbox_exec`: `./run.sh NAME 2 0 && cd p_NAME && higgsedit render . --out renders/NAME.mp4 --bitrate 20M && curl -f -X PUT -H "Content-Type: video/mp4" --upload-file renders/NAME.mp4 '<upload_url>'`.
  Then call `media_confirm` and `curl` the URL into the workspace. A 4K render takes about 3 s per second of
  graphic on XL.
- **Checking stills:** set `__FRAMES__` to 1, convert to JPG with PIL, and pass `image_paths` (512 KB in total) to
  `sandbox_exec`.
- **Gotchas:**
  - Fonts must be added per project (`higgsedit fonts add . Inter:400 Inter:600 Inter:700`); `run.sh` does this.
  - `overshoot` easing can't be used on a phase that animates opacity (values over 1 are refused); use `house`.
  - A counter needs a `layout="none"` wrapper that owns the timeline, plus a fixed-size child frame holding one
    text.
  - Counters have no thousands separator: count the thousands and place a static `,000` after them.
  - `icon` comes from the build context (`async ({ project, icon })`); components are arrow functions inside the
    default export.
  - Strike-throughs: a `clip` frame with `reveal={{from:"left"}}` over a 3 px rect.
  - Avoid banding with a dithered 4K JPG background (snippet below).

`run.sh` (create it in the sandbox once):
```bash
#!/bin/bash
# usage: ./run.sh NAME SCALE FRAMES   builds ~/mg/p_NAME from ~/mg/NAME.tpl.jsx (assets/ copied in)
set -e
n=$1; s=$2; f=$3
cd ~/mg; d=p_$n; rm -rf $d; mkdir -p $d; cp -r assets $d/
sed "s/__SCALE__/$s/; s/__FRAMES__/$f/" $n.tpl.jsx > $d/$n.jsx
cd $d
size=$(python3 -c "s=float('$s'); print(f'{int(1920*s)}x{int(1080*s)}')")
higgsedit init . --size $size --fps 30 >/dev/null
higgsedit fonts add . Inter:400 Inter:600 Inter:700 >/dev/null
higgsedit build $n.jsx 2>&1 | tail -8
```

Background (run in the workspace, then upload it as `assets/mg_bg.jpg`):
```python
import numpy as np; from PIL import Image
W,H=3840,2160; y,x=np.mgrid[0:H,0:W].astype(np.float32); nx,ny=(x-W/2)/(W/2),(y-H/2)/(H/2)
img=np.zeros((H,W,3),np.float32)+[16,15,14]
img+=(np.clip(1-np.sqrt((nx*.75)**2+((ny-.05)*.85)**2),0,1)**1.3)[...,None]*[16,13,11]
img+=np.exp(-(((x-W/2)/(W*.3))**2+((y-H*.66)/(H*.36))**2)*1.4)[...,None]*[13,6,3]
img+=np.random.default_rng(3).normal(0,.8,img.shape)
Image.fromarray(np.clip(img,0,255).astype(np.uint8)).save("mg_bg.jpg",quality=95,subsampling=0)
```

Kit template (`~/mg/NAME.tpl.jsx`; keep the kit, replace the scene):
```jsx
// Higgsedit motion-graphic template (house style: warm near-black, dark cards, Inter, coral accent).
// __SCALE__ 0.5 = quick stills, 2 = 3840x2160 final. __FRAMES__ 1 = write preview stills.
// Design every value in 1920x1080 units and wrap it in u().
const S = __SCALE__;
const u = (n) => Math.round(n * S * 100) / 100;
const W = 1920, H = 1080, DUR = 8.5;                 // DUR = the slot on the timeline, in seconds
const C = {
  text: "#F2EDE8", sub: "#A39B94", dim: "#6E6762", line: "#3A3431",
  card: "#262321", cardEdge: "#FFFFFF14", coral: "#E8825F",
  redBg: "#3B211D", redText: "#F0A496", green: "#4CC38A", greenBg: "#1E3328", greenText: "#9FE3C1",
};
const INTER = "Inter", house = "house";
const rise = (dy = 18, d = 0.55) => ({ enter: { from: { y: u(dy), opacity: 0 }, duration: d, easing: house } });

export default async ({ project, icon }) => {
  const p = await project({ size: `${u(W)}x${u(H)}`, fps: 30, background: "#0E0B0A" });
  const bg = await p.add("assets/mg_bg.jpg");              // dithered 4K background (no banding)
  const thumb = await p.add("assets/thumb.png");           // optional: a thumbnail/screenshot crop

  // ---- kit ----------------------------------------------------------------------------------
  const Label = ({ x, y, children }) => (
    <text x={u(x)} y={u(y)} width={u(500)} fontFamily={INTER} fontWeight={600} fontSize={u(14)}
      letterSpacing={u(2.6)} color={C.dim}>{children}</text>);
  const Pill = ({ at = 0, x, y, w, label, good }) => (
    <frame at={at} x={u(x)} y={u(y)} width={u(w)} height={u(54)} layout="none"
      motion={{ enter: { from: { x: u(-10), opacity: 0, scale: 0.92 }, duration: 0.45, easing: house } }}>
      <rect x={0} y={0} width={u(w)} height={u(54)} radius={u(27)} fill={good ? C.greenBg : C.redBg}
        strokeColor={good ? "#4CC38A55" : "#E5654F55"} strokeWidth={u(1.5)} />
      {good && <rect x={u(16)} y={u(14)} width={u(26)} height={u(26)} radius={u(13)} fill={C.green} />}
      {good && icon("check", { x: u(20), y: u(18), size: u(18), color: "#0F2419", strokeWidth: 3.2 })}
      <text x={u(good ? 52 : 0)} y={u(14)} width={u(good ? w - 60 : w)} align={good ? "left" : "center"}
        fontFamily={INTER} fontWeight={600} fontSize={u(21)} color={good ? C.greenText : C.redText}>{label}</text>
    </frame>);
  const Row = ({ at, x, y, w, label, value, color = C.text }) => (
    <frame at={at} x={u(x)} y={u(y)} width={u(w)} height={u(48)} layout="none"
      motion={{ enter: { from: { x: u(-18), opacity: 0 }, duration: 0.5, easing: house } }}>
      <text x={0} y={u(8)} width={u(300)} fontFamily={INTER} fontWeight={400} fontSize={u(24)} color="#CFC7C0">{label}</text>
      <path x={u(170)} y={u(30)} width={u(w - 320)} height={u(2)} d={`M0 1 L${u(w - 320)} 1`}
        stroke={{ width: u(2), color: "#4A433F", cap: "round" }} dash={[u(2), u(7)]} />
      <text x={u(w - 140)} y={u(4)} width={u(140)} align="right" fontFamily={INTER} fontWeight={600} fontSize={u(28)} color={color}>{value}</text>
    </frame>);
  // counter: a layout="none" wrapper owns the timeline; the target is a fixed-size child frame with ONE text
  const Counter = ({ at, x, y, w, h, size, from, to, suffix = "", prefix = "", dur = 1.5 }) => (
    <frame x={u(x)} y={u(y)} width={u(w)} height={u(h)} layout="none"
      motion={{ timeline: { at, duration: dur, easing: "ease-out", targets: [{ target: "Num", counter: { from, to, prefix, suffix } }] } }}>
      <frame name="Num" x={0} y={0} width={u(w)} height={u(h)} layout="none">
        <text x={0} y={0} width={u(w)} height={u(h)} align="right" fontFamily={INTER} fontWeight={600}
          fontSize={u(size)} letterSpacing={u(-3)} color={C.text}>{`${prefix}${to}${suffix}`}</text>
      </frame>
    </frame>);

  // ---- scene: a stats card (replace with this graphic's idea; keep the frame/background/push) ----
  const CX = 610, CY = 190, CW = 700, CH = 700, PAD = 44;
  p.compose(
    <frame x={0} y={0} width={u(W)} height={u(H)} layout="none">
      <media file={bg} x={0} y={0} width={u(W)} height={u(H)} fit="cover" />
      <frame x={0} y={0} width={u(W)} height={u(H)} layout="none"
        animate={[{ property: "scale", from: 1, to: 1.025, duration: DUR - 0.01, easing: "linear" }]}>
        <frame x={u(CX)} y={u(CY)} width={u(CW)} height={u(CH)} layout="none"
          motion={{ enter: { from: { y: u(40), opacity: 0, scale: 0.965 }, duration: 0.7, easing: house } }}>
          <rect x={0} y={0} width={u(CW)} height={u(CH)} radius={u(30)} fill={C.card} strokeColor={C.cardEdge}
            strokeWidth={u(1.5)} shadow={{ x: 0, y: u(30), blur: u(80), color: "#00000099" }} />
          <frame at={0.12} x={u(PAD)} y={u(PAD)} width={u(CW - 2 * PAD)} height={u(118)} layout="none" motion={rise(14)}>
            <media file={thumb} x={0} y={0} width={u(210)} height={u(118)} fit="cover" radius={u(12)} />
            <text x={u(236)} y={u(22)} width={u(400)} fontFamily={INTER} fontWeight={600} fontSize={u(25)} color={C.text}>Video title</text>
            <text x={u(236)} y={u(62)} width={u(400)} fontFamily={INTER} fontWeight={400} fontSize={u(19)} color={C.sub}>Channel  ·  12:47</text>
          </frame>
          <frame at={0.3} x={0} y={0} width={u(CW)} height={u(CH)} layout="none" motion={rise(12)}>
            <Label x={PAD} y={PAD + 160}>EDITOR'S VERDICT</Label>
          </frame>
          <Pill at={0.35} x={PAD} y={PAD + 190} w={300} label="Not worth uploading" />
          <Pill at={0.82} x={PAD + 322} y={PAD + 190} w={230} label="Posted anyway" good />
          <rect x={u(PAD)} y={u(PAD + 280)} width={u(CW - 2 * PAD)} height={u(1.5)} fill={C.line} />
          <frame at={1.2} x={0} y={0} width={u(CW)} height={u(CH)} layout="none" motion={rise(10, 0.45)}>
            <Label x={PAD} y={PAD + 312}>VIEWS</Label>
            <Counter at={0.24} x={PAD} y={PAD + 338} w={260} h={120} size={104} from={1} to={815} />
            <text x={u(PAD + 262)} y={u(PAD + 338)} width={u(220)} fontFamily={INTER} fontWeight={600}
              fontSize={u(104)} letterSpacing={u(-3)} color={C.text}>,000</text>
          </frame>
          <Row at={4.2} x={PAD} y={520} w={CW - 2 * PAD} label="Subscribers" value="+9,400" />
          <Row at={5.8} x={PAD} y={590} w={CW - 2 * PAD} label="Sales" value="$1,200" color={C.coral} />
        </frame>
      </frame>
    </frame>,
    { at: 0, dur: DUR, name: "MG" }
  );
  if (__FRAMES__) {
    await p.frame(0.6, "renders/a.png");
    await p.frame(DUR / 2, "renders/b.png");
    await p.frame(DUR - 0.2, "renders/c.png");
  }
};
```

## Troubleshooting

- **Empty timeline in CapCut:** it was open during the write. Have the viewer quit, check the md5 against the
  build, reinstall.
- **Red "media missing" clips:** a wrong path (a mount path, or the file moved). Compare with `device_paths.txt`.
- **A cue lands early or late:** whisper word times inside long run-on segments drift. Check the loudness printout
  and use a nearby cut.
- **Washed-out grey footage:** the camera recorded log (S-Log and similar) and needs a LUT. Ask before adding one,
  and never copy one from an old project by accident.
- **A graphic flashes or jumps:** re-run `overlays.py` on the current draft. The no-flash snap runs every time.

## Scripts

Write each one to `work/scripts/` exactly as shown. They import `cct.py`.

### `cct.py`
```python
"""Shared helpers for the CapCut talking-head workflow."""
import json, os, uuid

FPS = 30


def U():
    return str(uuid.uuid4()).upper()


def fr(t, fps=FPS):
    return int(round(t * fps))


def us(frames, fps=FPS):
    """frames -> CapCut microseconds (CapCut floors to the microsecond)."""
    return int(frames * 1000000 // fps)


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save(p, obj, compact=False):
    os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        if compact:
            f.write(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))
        else:
            json.dump(obj, f, ensure_ascii=False, indent=1)


def runs(mask):
    """[(start, end)) index runs where mask is True."""
    out, i, n = [], 0, len(mask)
    while i < n:
        if mask[i]:
            j = i
            while j < n and mask[j]:
                j += 1
            out.append((i, j))
            i = j
        else:
            i += 1
    return out


def snap_to_cuts(items, cuts, thr=0.5, eps=0.02):
    """No camera flashes next to an overlay (graphic or cutaway).

    items: dicts with 'a', 'b' (timeline seconds), optional 'max_dur' (how long it may become) and 'name'.
    cuts:  times where the picture underneath changes (camera cuts, other overlays' edges, 0, end).
    Rules (thr = 0.5 s = 15 frames at 30 fps):
      - an overlay that starts < thr after a cut starts ON that cut;
      - an overlay that ends < thr before the next cut stretches to it (within max_dur), otherwise ends on the
        last cut inside it when that is < thr before its end;
      - a gap < thr between two overlays is closed (the first one stretches, else the second starts earlier).
    Returns a list of human-readable changes."""
    cuts = sorted(set(round(c, 4) for c in cuts))
    items = sorted(items, key=lambda x: x["a"])
    log = []
    prev_end = 0.0
    for it in items:
        a, b = it["a"], it["b"]
        maxd = it.get("max_dur") or 1e9
        before = [c for c in cuts if c <= a + eps]
        if before:
            p = before[-1]
            if eps < a - p < thr and p >= prev_end - eps:
                log.append(f"{it.get('name', '?')}: start {a:.3f} -> {p:.3f} (was {round((a - p) * 30)}f after a cut)")
                a = p
        after = [c for c in cuts if c >= b - eps]
        if after:
            n = after[0]
            if eps < n - b < thr:
                if n - a <= maxd + eps:
                    log.append(f"{it.get('name', '?')}: end {b:.3f} -> {n:.3f} (camera showed {round((n - b) * 30)}f)")
                    b = n
                else:
                    inside = [c for c in cuts if a + 1.0 < c < b - eps]
                    if inside and b - inside[-1] < thr:
                        log.append(f"{it.get('name', '?')}: end {b:.3f} -> {inside[-1]:.3f} (could not stretch)")
                        b = inside[-1]
        it["a"], it["b"] = a, b
        prev_end = b
    for x, y in zip(items, items[1:]):
        gap = y["a"] - x["b"]
        if eps < gap < thr:
            if y["a"] - x["a"] <= (x.get("max_dur") or 1e9) + eps:
                log.append(f"{x.get('name', '?')}: end {x['b']:.3f} -> {y['a']:.3f} (closes a {round(gap * 30)}f gap)")
                x["b"] = y["a"]
            else:
                log.append(f"{y.get('name', '?')}: start {y['a']:.3f} -> {x['b']:.3f} (closes a {round(gap * 30)}f gap)")
                y["a"] = x["b"]
    return log


def all_materials(draft):
    m = {}
    for k, v in draft["materials"].items():
        if isinstance(v, list):
            for o in v:
                if isinstance(o, dict) and "id" in o:
                    m[o["id"]] = (k, o)
    return m


def validate(draft):
    """Refuse a draft CapCut would choke on: dangling refs, duplicate ids, overlaps, keys outside clips."""
    ids = set()
    for k, v in draft["materials"].items():
        if isinstance(v, list):
            for x in v:
                if isinstance(x, dict) and "id" in x:
                    assert x["id"] not in ids, ("duplicate material id", k)
                    ids.add(x["id"])
    total = draft["duration"]
    for ti, tr in enumerate(draft["tracks"]):
        prev = -1
        for s in tr["segments"]:
            assert s["material_id"] in ids, ("missing material", ti)
            assert all(r in ids for r in s["extra_material_refs"]), ("missing extra material", ti)
            st, du = s["target_timerange"]["start"], s["target_timerange"]["duration"]
            assert du > 0 and st >= prev, (tr["type"], "overlap or empty clip at", st / 1e6)
            assert st + du <= total + 1, (tr["type"], "clip runs past the end", (st + du) / 1e6)
            src = s.get("source_timerange")
            if src:
                for k in s.get("common_keyframes") or []:
                    for p in k["keyframe_list"]:
                        assert src["start"] <= p["time_offset"] < src["start"] + src["duration"] + 1, \
                            ("keyframe outside its clip", tr["type"], st / 1e6)
            prev = st + du
    main = draft["tracks"][0]["segments"]
    assert main[0]["target_timerange"]["start"] == 0, "main track must start at 0"
    for a, b in zip(main, main[1:]):
        assert a["target_timerange"]["start"] + a["target_timerange"]["duration"] == b["target_timerange"]["start"], \
            ("gap on the main track at", b["target_timerange"]["start"] / 1e6)
    return True
```

### `analyze.py`
```python
"""Transcribe the camera audio with word timings and measure loudness every 10 ms.

usage: python3 analyze.py WORK_DIR [--model small.en]
  needs WORK_DIR/camera_16k.wav (16 kHz mono PCM, extracted on the viewer's computer with ffmpeg)
  writes words.json (every word: i, w, s, e, p), db10ms.npy, phrases.txt (lines split at pauses)
"""
import json, sys, wave
import numpy as np

work = sys.argv[1]
model_name = sys.argv[sys.argv.index("--model") + 1] if "--model" in sys.argv else "small.en"

wf = wave.open(f"{work}/camera_16k.wav")
assert wf.getframerate() == 16000 and wf.getnchannels() == 1, "expected 16 kHz mono"
a = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768

# loudness envelope (dBFS per 10 ms): cut points are snapped to its quiet stretches
hop = 160
n = len(a) // hop
db = 20 * np.log10(np.sqrt((a[: n * hop].reshape(n, hop) ** 2).mean(1) + 1e-12))
np.save(f"{work}/db10ms.npy", db)

from faster_whisper import WhisperModel   # noqa: E402
m = WhisperModel(model_name, device="cpu", compute_type="int8")
# condition_on_previous_text=False keeps more repeats/false starts instead of smoothing them away.
# Pass the array, not a path: some PyAV builds break faster-whisper's own decoder.
segs, _ = m.transcribe(a, word_timestamps=True, condition_on_previous_text=False,
                       vad_filter=False, beam_size=5, temperature=0)
words = []
for s in segs:
    for w in s.words:
        words.append({"i": len(words), "w": w.word, "s": round(w.start, 3), "e": round(w.end, 3),
                      "p": round(w.probability, 3)})
    print(f"{s.start:7.2f} {s.text.strip()}", flush=True)
json.dump(words, open(f"{work}/words.json", "w"))

with open(f"{work}/phrases.txt", "w") as f:
    line, prev = [], None
    for w in words:
        if line and w["s"] - line[-1]["e"] > 0.3:
            f.write(f"[{line[0]['i']:4d}] {line[0]['s']:7.2f}-{line[-1]['e']:7.2f} {''.join(x['w'] for x in line).strip()}\n")
            line = []
        line.append(w)
    if line:
        f.write(f"[{line[0]['i']:4d}] {line[0]['s']:7.2f}-{line[-1]['e']:7.2f} {''.join(x['w'] for x in line).strip()}\n")
print(f"{len(words)} words, {len(a) / 16000:.1f}s -> {work}/words.json, phrases.txt, db10ms.npy")
```

### `edl.py`
```python
"""Cut list: what to keep from the camera file, how each clip is framed, where cutaways land.

usage: python3 edl.py WORK_DIR        (reads WORK_DIR/job.json, words.json, db10ms.npy)
writes WORK_DIR/edl.json and WORK_DIR/words_tl.json (every word's time on the edited timeline)

job.json fields (seconds are camera-file seconds; word ranges are inclusive indices from words.json):
  pacing        "tight" (breath-length pauses) | "natural" (only pauses over 0.6 s go)
  punch         alternate framing on jump cuts, e.g. 1.12; 0 or 1 disables punch-ins
  end_hold      seconds of picture kept after the last word (music ring-out), default 2.0
  remove_words  [[first, last, "why"], ...]   repeats, false starts, resets
  remove_time   [[start, end, "why"], ...]    for repeats the transcript merged into one word run
  force_start   {"<first word index>": seconds}   removal start where there is no silence
  force_end     {"<last word index>": seconds}    removal end override
  zooms         [[first, last, "why"], ...]   intriguing lines: slow push-in, pauses kept longer
  inserts       [{"a": word, "b": word, "device": "/real/path", "kind": "photo"|"video", "w": px, "h": px,
                  "src": seconds into a video, "file_dur": video length, "name": "..."},
                 {"a":..,"b":.., "kind": "photo_seq", "devices": [...], "w":.., "h":..}]   (seq = split evenly)
"""
import json, sys
import numpy as np
import cct

work = sys.argv[1]
J = cct.load(f"{work}/job.json")
FPS = J.get("fps", 30)
W = cct.load(f"{work}/words.json")
db = np.load(f"{work}/db10ms.npy")
N = len(db)
SIL = -50.0
PACE = {"tight": (0.45, 0.12, 0.10), "natural": (0.60, 0.20, 0.15)}[J.get("pacing", "tight")]
ZOOM_PACE = (0.80, 0.22, 0.16)
T = lambda i, end=False: W[i]["e"] if end else W[i]["s"]


def silences(t0, t1, thr=SIL, min_len=0.03):
    a, b = max(0, int(t0 * 100)), min(N, int(t1 * 100))
    return [((a + x) / 100, (a + y) / 100) for x, y in cct.runs(db[a:b] < thr) if (y - x) / 100 >= min_len]


def gap_between(i, j):
    t0, t1 = T(i, True) - 0.25, T(j) + 0.25
    c = silences(t0, t1) or silences(t0, t1, thr=-45)
    if not c:
        m = (T(i, True) + T(j)) / 2
        return (m, m)
    return max(c, key=lambda r: r[1] - r[0])


def local_min(t, win=0.08):
    a, b = int((t - win) * 100), int((t + win) * 100)
    return (a + int(np.argmin(db[a:b]))) / 100


# ---- removals -> time ranges, each edge snapped into a silence
fs = {int(k): v for k, v in J.get("force_start", {}).items()}
fe = {int(k): v for k, v in J.get("force_end", {}).items()}
removed = []
for a, b, why in J.get("remove_words", []):
    if a in fs:
        s = local_min(fs[a])
    else:
        g = gap_between(a - 1, a)
        s = min(g[1], g[0] + 0.12)
    if b in fe:
        e = fe[b]
    else:
        g = gap_between(b, b + 1)
        e = max(g[0], g[1] - 0.08)
    removed.append((s, e, why))
removed += [tuple(r) for r in J.get("remove_time", [])]
removed.sort()

# ---- speech mask
speech = db > SIL
for x, y in cct.runs(~speech):
    if y - x < 12:
        speech[x:y] = True          # stop consonants are not pauses
for x, y in cct.runs(speech):
    if y - x < 6:
        speech[x:y] = False         # clicks are not speech

zoom_src = [(T(a) - 0.05, T(b, True) + 0.12, why) for a, b, why in J.get("zooms", [])]
in_zoom = lambda t: any(z0 <= t <= z1 for z0, z1, _ in zoom_src)
end_src = J.get("end_src") or (W[-1]["e"] + 0.6)

keep = np.zeros(N, bool)
keep[max(0, int(np.argmax(speech)) - 8):int(end_src * 100)] = True
for s, e, _ in removed:
    keep[int(round(s * 100)):int(round(e * 100))] = False
for x, y in cct.runs(~speech):
    if x == 0 or y >= N:
        continue
    t0, t1 = x / 100, y / 100
    min_gap, tail, lead = ZOOM_PACE if in_zoom((t0 + t1) / 2) else PACE
    if t1 - t0 >= min_gap:
        keep[int(round((t0 + tail) * 100)):int(round((t1 - lead) * 100))] = False

clips = [(x / 100, y / 100) for x, y in cct.runs(keep)]
removal_ends = {round(e, 2) for _, e, _ in removed}


def merge_short(clips, min_len=0.7, max_restore=1.0):
    changed = True
    while changed:
        changed = False
        for k, (a, b) in enumerate(clips):
            if b - a >= min_len:
                continue
            opts = []
            if k > 0 and a - clips[k - 1][1] <= max_restore and round(a, 2) not in removal_ends:
                opts.append((a - clips[k - 1][1], k - 1))
            if k + 1 < len(clips) and clips[k + 1][0] - b <= max_restore and round(clips[k + 1][0], 2) not in removal_ends:
                opts.append((clips[k + 1][0] - b, k))
            if opts:
                _, j = min(opts)
                clips[j:j + 2] = [(clips[j][0], clips[j + 1][1])]
                changed = True
                break
    return clips


clips = merge_short(clips)
has_words = lambda a, b: any(w["s"] < b - 0.05 and w["e"] > a + 0.05 for w in W)
dropped = [(a, b) for a, b in clips if not has_words(a, b)]
clips = [(a, b) for a, b in clips if has_words(a, b)]
clips_f = [[cct.fr(a, FPS), cct.fr(b, FPS)] for a, b in clips if cct.fr(b, FPS) - cct.fr(a, FPS) >= 3]
clips_f[-1][1] = max(clips_f[-1][1], cct.fr(W[-1]["e"] + J.get("end_hold", 2.0), FPS))

# split at zoom edges so a push-in starts/stops on its words (invisible: same source, same scale)
bounds = sorted({cct.fr(z0, FPS) for z0, _, _ in zoom_src} | {cct.fr(z1, FPS) for _, z1, _ in zoom_src})
split = []
for fa, fb in clips_f:
    inner = [x for x in bounds if fa + 9 < x < fb - 9]
    pts = [fa] + inner + [fb]
    for p, q in zip(pts, pts[1:]):
        split.append({"src0": p, "src1": q, "cont": p in inner})
tl = 0
for c in split:
    c["tl0"] = tl
    tl += c["src1"] - c["src0"]
    c["tl1"] = tl
TOTAL = tl


def src_to_tl(t):
    f = t * FPS
    for c in split:
        if c["src0"] <= f < c["src1"]:
            return (c["tl0"] + f - c["src0"]) / FPS
    for c in split:
        if c["src0"] >= f:
            return c["tl0"] / FPS
    return TOTAL / FPS


# ---- framing: punch-ins on jump cuts, slow push-ins on intriguing lines
PUNCH = J.get("punch", 1.12) or 1.0
zones = [{"tl0": src_to_tl(z0), "tl1": src_to_tl(z1), "why": why} for z0, z1, why in zoom_src]
for z in zones:
    z["dur"] = z["tl1"] - z["tl0"]
prev_end, active = PUNCH, None
for c in split:
    mid = (c["tl0"] + c["tl1"]) / 2 / FPS
    z = next((zz for zz in zones if zz["tl0"] <= mid <= zz["tl1"]), None)
    if z is not None:
        if z is not active:
            s0 = prev_end if c["cont"] else (1.0 if prev_end >= 1.06 else min(1.06, PUNCH))
            amt = min(0.09, max(0.04, 0.012 * z["dur"]), 1.18 - s0)
            z["s0"], z["s1"], active = s0, s0 + amt, z
        ramp = lambda t: z["s0"] + (z["s1"] - z["s0"]) * min(1, max(0, (t - z["tl0"]) / max(1e-6, z["dur"])))
        c["scale0"], c["scale1"] = round(ramp(c["tl0"] / FPS), 4), round(ramp((c["tl1"] - 1) / FPS), 4)
        c["zoom"] = z["why"]
    else:
        active = None
        s = prev_end if c["cont"] else (1.0 if prev_end >= 1.06 else PUNCH)
        c["scale0"] = c["scale1"] = s
        c["zoom"] = None
    prev_end = c["scale1"]

# ---- cutaways on the words that mention them, then snapped so no camera flashes beside them
cam_cuts = [c["tl0"] / FPS for c in split if not c["cont"]] + [TOTAL / FPS]
items = []
for k, it in enumerate(J.get("inserts", [])):
    a = src_to_tl(T(it["a"]) - 0.05)
    b = src_to_tl(T(it["b"], True) + 0.15)
    x = dict(it, a=a, b=b, name=it.get("name", f"insert {k + 1}"))
    if it["kind"] == "video":
        x["max_dur"] = it["file_dur"] - it.get("src", 0.0) - 1.0 / FPS
        x["b"] = min(b, a + x["max_dur"])
    items.append(x)
snap_log = cct.snap_to_cuts(items, cam_cuts)
ins_out = []
for x in items:
    f0, f1 = cct.fr(x["a"], FPS), cct.fr(x["b"], FPS)
    if x["kind"] == "photo_seq":
        n = len(x["devices"])
        step = (f1 - f0) // n
        for k, dev in enumerate(x["devices"]):
            a = f0 + k * step
            ins_out.append({"device": dev, "kind": "photo", "w": x["w"], "h": x["h"], "tl0": a,
                            "tl1": f1 if k == n - 1 else a + step, "src": 0.0, "name": f"{x['name']} {k + 1}/{n}"})
    else:
        ins_out.append({"device": x["device"], "kind": x["kind"], "w": x["w"], "h": x["h"], "tl0": f0, "tl1": f1,
                        "src": x.get("src", 0.0), "file_dur": x.get("file_dur"), "name": x["name"]})

def to_tl(t):
    f = t * FPS
    for c in split:
        if c["src0"] <= f < c["src1"]:
            return round((c["tl0"] + f - c["src0"]) / FPS, 3)
    return None


words_tl = [{"i": w["i"], "w": w["w"].strip(), "s": to_tl(w["s"] + 0.02), "e": to_tl(max(w["s"] + 0.03, w["e"] - 0.02))}
            for w in W]
cct.save(f"{work}/words_tl.json", words_tl)
cct.save(f"{work}/edl.json", {"fps": FPS, "total_frames": TOTAL, "clips": split, "inserts": ins_out, "zones": zones,
                              "removed": [{"s": s, "e": e, "why": w} for s, e, w in removed],
                              "cam_cuts": cam_cuts, "snaps": snap_log})

lens = np.array([(c["src1"] - c["src0"]) / FPS for c in split if not c["cont"]])
print(f"timeline {TOTAL / FPS:.1f}s ({int(TOTAL / FPS // 60)}:{TOTAL / FPS % 60:04.1f}) from {end_src:.1f}s; "
      f"{len(split)} clips, {sum(1 for c in split if not c['cont']) - 1} cuts; shortest clip {lens.min():.2f}s")
print("dropped wordless stretches:", [(round(a, 2), round(b, 2)) for a, b in dropped])
for s, e, w in removed:
    print(f"removed {s:7.2f}-{e:7.2f} ({e - s:5.2f}s) {w}")
for i in ins_out:
    print(f"cutaway {i['tl0'] / FPS:7.2f}-{i['tl1'] / FPS:7.2f} {i['name']}")
for z in zones:
    print(f"push-in {z['tl0']:7.2f}-{z['tl1']:7.2f} {z.get('s0', 0):.3f}->{z.get('s1', 0):.3f} {z['why']}")
for line in snap_log:
    print("snap:", line)
```

### `qa.py`
```python
"""Re-transcribe the EDITED audio and read it back: the first transcript merges repeats ("another example,
another example"), so leftover stumbles only show up here.

usage: python3 qa.py WORK_DIR [START END]    (seconds on the edited timeline; default: everything)
writes WORK_DIR/qa_transcript.txt
"""
import sys, wave
import numpy as np
import cct

work = sys.argv[1]
E = cct.load(f"{work}/edl.json")
FPS = E["fps"]
wf = wave.open(f"{work}/camera_16k.wav")
a = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768
x = np.concatenate([a[int(round(c["src0"] / FPS * 16000)):][:int(round((c["tl1"] - c["tl0"]) / FPS * 16000))]
                    for c in E["clips"]])
t0, t1 = (float(sys.argv[2]), float(sys.argv[3])) if len(sys.argv) > 3 else (0.0, len(x) / 16000)
from faster_whisper import WhisperModel   # noqa: E402
m = WhisperModel("small.en", device="cpu", compute_type="int8")
segs, _ = m.transcribe(x[int(t0 * 16000):int(t1 * 16000)], condition_on_previous_text=False, beam_size=5, temperature=0)
with open(f"{work}/qa_transcript.txt", "w") as f:
    for s in segs:
        line = f"{t0 + s.start:7.2f} {s.text.strip()}"
        f.write(line + "\n")
        print(line, flush=True)
```

### `harvest.py`
```python
"""Harvest CapCut object templates from the viewer's OWN saved projects, so every object we write is one their
CapCut version already wrote itself.

usage: python3 harvest.py OUT_templates.json DRAFT_INFO.json [DRAFT_INFO.json ...]
Needs, across the drafts given (any mix): a video clip on the main track, an audio clip (music), and an
adjustment layer. A photo clip is used if present (otherwise derived from the video material).
"""
import copy, json, sys
import cct

out, paths = sys.argv[1], sys.argv[2:]
T = {"source": [], "version": None}


# per-clip looks (LUTs, HSL, curves, filters, masks) must never ride along into a new edit
LOOKS = ("effects", "hsl", "color_curves", "hsl_curves", "primary_color_wheels", "log_color_wheels", "video_effects",
         "common_mask", "chromas", "beats", "audio_effects", "realtime_denoises", "audio_track_indexes")


def refs_of(draft, seg):
    m = cct.all_materials(draft)
    return [[m[r][0], copy.deepcopy(m[r][1])] for r in seg["extra_material_refs"] if r in m and m[r][0] not in LOOKS]


for p in paths:
    try:
        d = cct.load(p)
    except Exception:
        print("skipped (not plain JSON):", p)
        continue
    m = cct.all_materials(d)
    ver = (d.get("last_modified_platform") or d.get("platform") or {}).get("app_version")
    used = False
    for ti, tr in enumerate(d["tracks"]):
        for s in tr["segments"]:
            kind, mat = m.get(s["material_id"], (None, {}))
            if tr["type"] == "video" and kind == "videos" and mat.get("type") == "video" and "video_segment" not in T:
                T["video_segment"] = copy.deepcopy(s)
                T["video_refs"] = refs_of(d, s)
                T["video_material"] = copy.deepcopy(mat)
                used = True
            if tr["type"] == "video" and kind == "videos" and mat.get("type") == "photo" and "photo_material" not in T:
                T["photo_material"] = copy.deepcopy(mat)
                used = True
            if tr["type"] == "audio" and kind == "audios" and "audio_segment" not in T:
                r = refs_of(d, s)
                if any(k == "audio_fades" for k, _ in r):
                    T["audio_segment"] = copy.deepcopy(s)
                    T["audio_refs"] = r
                    T["audio_material"] = copy.deepcopy(mat)
                    used = True
            if tr["type"] == "adjust" and "adjust_segment" not in T:
                T["adjust_track"] = {k: v for k, v in tr.items() if k != "segments"}
                T["adjust_segment"] = copy.deepcopy(s)
                T["adjust_placeholder"] = copy.deepcopy(mat)
                T["adjust_refs"] = [[m[r][0], copy.deepcopy(m[r][1])] for r in s["extra_material_refs"] if r in m]
                used = True
    if used:
        T["source"].append(p)
        T["version"] = T["version"] or ver

missing = [k for k in ("video_segment", "audio_segment", "adjust_segment") if k not in T]
if "photo_material" not in T and "video_material" in T:
    pm = copy.deepcopy(T["video_material"])
    pm.update(type="photo", duration=10800000000, has_audio=False)
    T["photo_material"] = pm
if "adjust_refs" in T:
    effects = [o for k, o in T["adjust_refs"] if k == "effects"]
    have = {o.get("type") for o in effects}
    if effects:
        for need in ("saturation", "contrast", "shadow"):
            if need not in have:                       # same effect bundle, different parameter
                e = copy.deepcopy(effects[0])
                e.update(type=need, value=0.0)
                T["adjust_refs"].append(["effects", e])
cct.save(out, T)
print("templates from", T["source"], "CapCut", T["version"])
print("MISSING:", missing if missing else "nothing")
```

### `build.py`
```python
"""Write the CapCut timeline: camera clips (punch-ins + push-ins), adjustment layer, cutaways on a dark plate, music.

usage: python3 build.py WORK_DIR PROJECT_COPY_DIR OUT_DIR
  WORK_DIR:  job.json, edl.json, music.json, templates.json, camera_16k.wav
  PROJECT_COPY_DIR: copies of the (empty) target project's draft_info.json (or draft_content.json),
                    draft_meta_info.json and Timelines/project.json
job.json also needs:
  camera: {"device": "/real/path/cam.mp4", "w": 3840, "h": 2160, "dur_us": 839166000}   (dur_us from the media bin)
  plate:  {"device": "/real/path/Insert Background.png"}      dark background behind cutaways
  grade:  {"saturation": 0.15, "contrast": 0.10, "shadow": -0.10}
  music_below_voice_db: 15
music.json: [{"device": "/real/path/track.mp3", "local": "staged copy", "start": 0, "end": 105.7,
              "src": 0 | "align": [music_seconds, timeline_seconds], "fin": 0, "fout": 1.2}, ...]
"""
import copy, hashlib, json, os, re, subprocess, sys, time
import cct

work, proj, outd = sys.argv[1:4]
J, E = cct.load(f"{work}/job.json"), cct.load(f"{work}/edl.json")
T = cct.load(f"{work}/templates.json")
MUSIC = cct.load(f"{work}/music.json") if os.path.exists(f"{work}/music.json") else []
FPS = E["fps"]
us = lambda f: cct.us(f, FPS)

name = next(n for n in ("draft_info.json", "draft_content.json") if os.path.exists(f"{proj}/{n}"))
raw = open(f"{proj}/{name}", "rb").read()
assert raw.lstrip()[:1] == b"{", "this CapCut build encrypts projects; it cannot be edited from outside"
skel = cct.load(f"{proj}/{name}")
meta = cct.load(f"{proj}/draft_meta_info.json")
tl_id = cct.load(f"{proj}/Timelines/project.json").get("main_timeline_id") if os.path.exists(f"{proj}/Timelines/project.json") else None

M = copy.deepcopy(skel["materials"])
for k in M:
    if isinstance(M[k], list):
        M[k] = []


def add(kind, tmpl, **kw):
    o = copy.deepcopy(tmpl)
    o["id"] = cct.U()
    o.update(kw)
    M.setdefault(kind, []).append(o)
    return o["id"]


def refs(pairs, speed=None, skip=()):
    out = []
    for kind, o in pairs:
        if kind in skip:
            continue
        kw = {"speed": float(speed)} if (kind == "speeds" and speed is not None) else {}
        out.append(add(kind, o, **kw))
    return out


def kf(prop, pts):
    return {"id": cct.U(), "material_id": "", "property_type": prop,
            "keyframe_list": [{"id": cct.U(), "curveType": "Line", "time_offset": int(t), "left_control": {"x": 0.0, "y": 0.0},
                               "right_control": {"x": 0.0, "y": 0.0}, "values": [float(v)], "string_value": "",
                               "graphID": ""} for t, v in pts]}


def track(kind, flag=0):
    return {"id": cct.U(), "type": kind, "flag": flag, "attribute": 0, "name": "", "is_default_name": True, "segments": []}


def vseg(mid, src_us, dur_us, tl_us, s0, s1, vol, keyed, speed=1.0):
    s = copy.deepcopy(T["video_segment"])
    s.update({"id": cct.U(), "material_id": mid, "extra_material_refs": refs(T["video_refs"], speed=speed),
              "source_timerange": {"start": src_us, "duration": int(round(dur_us * speed))},
              "target_timerange": {"start": tl_us, "duration": dur_us}, "speed": float(speed),
              "volume": float(vol), "last_nonzero_volume": 1.0, "keyframe_refs": [], "render_index": 0,
              "track_render_index": 0})
    s["clip"] = {"scale": {"x": s0, "y": s0}, "rotation": 0.0, "transform": {"x": 0.0, "y": 0.0},
                 "flip": {"vertical": False, "horizontal": False}, "alpha": 1.0}
    s["uniform_scale"] = {"on": True, "value": 1.0}
    if keyed:   # keyframe times are SOURCE time: clip source start + offset; last key one frame before the end
        a, b = src_us, src_us + s["source_timerange"]["duration"] - us(1)
        s["common_keyframes"] = [kf("KFTypePositionX", [(a, 0), (b, 0)]), kf("KFTypePositionY", [(a, 0), (b, 0)]),
                                 kf("KFTypeScaleX", [(a, s0), (b, s1)]), kf("KFTypeRotation", [(a, 0), (b, 0)])]
    else:
        s["common_keyframes"] = []
    return s


def lufs(path):
    r = subprocess.run(["ffmpeg", "-nostats", "-i", path, "-af", "ebur128", "-f", "null", "-"], capture_output=True, text=True)
    return float(re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)[-1])


# 1 camera
cam = J["camera"]
main = track("video")
for c in E["clips"]:
    tl_us = us(c["tl0"])
    dur_us = us(c["tl1"]) - tl_us
    src_us = us(c["src0"])
    assert src_us + dur_us <= cam["dur_us"], "clip runs past the end of the camera file"
    mid = add("videos", T["video_material"], path=cam["device"], material_name=os.path.basename(cam["device"]),
              width=cam["w"], height=cam["h"], duration=cam["dur_us"], unique_id="", local_material_id="", media_path="")
    main["segments"].append(vseg(mid, src_us, dur_us, tl_us, c["scale0"], c["scale1"], 1.0,
                                 abs(c["scale1"] - c["scale0"]) > 1e-4))
TOTAL = us(E["total_frames"])
tracks = [main]

# 2 adjustment layer (sits under the overlays, so screen recordings keep their true colour)
if "adjust_segment" in T and J.get("grade"):
    adj = dict(copy.deepcopy(T["adjust_track"]), id=cct.U(), segments=[])
    s = copy.deepcopy(T["adjust_segment"])
    rr = []
    for kind, o in T["adjust_refs"]:
        if kind == "effects":
            if o.get("type") in J["grade"]:
                rr.append(add("effects", o, value=float(J["grade"][o["type"]])))
        else:
            rr.append(add(kind, o))
    s.update({"id": cct.U(), "material_id": add("placeholders", T["adjust_placeholder"]), "extra_material_refs": rr,
              "target_timerange": {"start": 0, "duration": TOTAL}, "keyframe_refs": [], "common_keyframes": []})
    adj["segments"].append(s)
    tracks.append(adj)

# 3 cutaways: dark plate + picture fitted at 88% easing to ~92%, muted
if E["inserts"]:
    plate_tr, ins_tr = track("video", 2), track("video", 2)
    for it in E["inserts"]:
        tl_us = us(it["tl0"])
        dur_us = us(it["tl1"]) - tl_us
        amt = round(min(0.05, max(0.015, 0.004 * dur_us / 1e6)), 4)
        pm = add("videos", T["photo_material"], path=J["plate"]["device"], material_name=os.path.basename(J["plate"]["device"]),
                 width=1920, height=1080, unique_id="", local_material_id="", media_path="")
        plate_tr["segments"].append(vseg(pm, 0, dur_us, tl_us, 1.0, 1.0, 0.0, False))
        if it["kind"] == "video":
            fd = int(it["file_dur"] * 1e6)
            mid = add("videos", T["video_material"], path=it["device"], material_name=os.path.basename(it["device"]),
                      width=it["w"], height=it["h"], duration=fd, unique_id="", local_material_id="", media_path="")
            src_us = us(round(it["src"] * FPS))
            assert src_us + dur_us <= fd, (it["name"], "cutaway runs past the end of its file")
        else:
            mid = add("videos", T["photo_material"], path=it["device"], material_name=os.path.basename(it["device"]),
                      width=it["w"], height=it["h"], unique_id="", local_material_id="", media_path="")
            src_us = 0
        ins_tr["segments"].append(vseg(mid, src_us, dur_us, tl_us, 0.88, round(0.88 + amt, 4), 0.0, True))
    tracks += [plate_tr, ins_tr]

# 4 music, alternating two tracks so sections can crossfade
voice = lufs(f"{work}/camera_16k.wav")
mus = [track("audio"), track("audio")]
for k, m in enumerate(MUSIC):
    fdur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", m["local"]],
                                capture_output=True, text=True).stdout)
    src = m["align"][0] - (m["align"][1] - m["start"]) if "align" in m else m.get("src", 0.0)
    src = max(0.0, round(src * FPS) / FPS)
    tl_us = us(cct.fr(m["start"], FPS))
    dur_us = us(cct.fr(m["end"], FPS)) - tl_us
    src_us = us(cct.fr(src, FPS))
    dur_us = min(dur_us, int(fdur * 1e6) - src_us - us(1))
    vol = 10 ** (((voice - J.get("music_below_voice_db", 15)) - lufs(m["local"])) / 20)
    aid = add("audios", T["audio_material"], name=os.path.basename(m["device"]), path=m["device"],
              duration=int(fdur * 1e6), unique_id="", local_material_id="")
    rr = []
    for kind, o in T["audio_refs"]:
        if kind == "audio_fades":
            rr.append(add(kind, o, fade_in_duration=int(m.get("fin", 1.2) * 1e6), fade_out_duration=int(m.get("fout", 1.2) * 1e6)))
        else:
            rr.append(add(kind, o, **({"speed": 1.0} if kind == "speeds" else {})))
    s = copy.deepcopy(T["audio_segment"])
    s.update({"id": cct.U(), "material_id": aid, "extra_material_refs": rr, "source_timerange": {"start": src_us, "duration": dur_us},
              "target_timerange": {"start": tl_us, "duration": dur_us}, "volume": round(vol, 5), "last_nonzero_volume": 1.0,
              "speed": 1.0, "keyframe_refs": [], "common_keyframes": [], "render_index": 0})
    mus[k % 2]["segments"].append(s)
tracks += [t for t in mus if t["segments"]]

for i, tr in enumerate(tracks):
    for s in tr["segments"]:
        s["track_render_index"] = i
        if tr["type"] == "video" and tr["flag"] == 2:
            s["render_index"] = i
D = copy.deepcopy(skel)
D.update(tracks=tracks, materials=M, duration=TOTAL, fps=float(FPS))
D["keyframes"] = {k: [] for k in (skel.get("keyframes") or {})}
cct.validate(D)

os.makedirs(outd, exist_ok=True)
blob = json.dumps(D, ensure_ascii=False, separators=(",", ":"))
open(f"{outd}/{name}", "w", encoding="utf-8").write(blob)
meta.update(tm_duration=TOTAL, tm_draft_modified=int(time.time() * 1e6))
cct.save(f"{outd}/draft_meta_info.json", meta, compact=True)
targets = [name, name + ".bak", "template-2.tmp"] + ([f"Timelines/{tl_id}/{n}" for n in (name, name + ".bak", "template-2.tmp")] if tl_id else [])
open(f"{outd}/install_targets.txt", "w").write("\n".join(targets) + "\n")
paths = sorted({m["path"] for m in M["videos"]} | {m["path"] for m in M["audios"]})
open(f"{outd}/device_paths.txt", "w").write("\n".join(paths) + "\n")
md5 = hashlib.md5(blob.encode("utf-8")).hexdigest()
cct.save(f"{outd}/build_report.json", {"md5": md5, "seconds": TOTAL / 1e6, "voice_lufs": voice,
                                       "tracks": [(t["type"], t["flag"], len(t["segments"])) for t in tracks]})
print(f"built {name}: {[(t['type'], len(t['segments'])) for t in tracks]}, {TOTAL / 1e6:.2f}s, md5 {md5}")
```

### `place_graphics.py`
```python
"""Place finished motion graphics on the lines they belong to (phrase-anchored, so it survives re-edits).

usage: python3 place_graphics.py WORK_DIR        (reads graphics.json + words_tl.json, writes overlays.json)
graphics.json: [{"name": "MG01 Editor Verdict", "device": "/real/path/MG01.mp4", "file_dur": 8.2,
                 "start_phrase": "I posted it anyways",        first words the graphic should land on
                 "end_phrase": "in sales",                     optional: stretch/squeeze (0.8x-1.25x) to end here
                 "lead": 0.1,                                  seconds before the first word (default 0.1)
                 "kind": "chapter" | "explainer"}, ...]
Graphics made for an exact window (e.g. built in Higgsfield for this edit) can give "a"/"b" seconds instead.
"""
import re, sys
import cct

work = sys.argv[1]
G = cct.load(f"{work}/graphics.json")
W = [w for w in cct.load(f"{work}/words_tl.json") if w["s"] is not None]
norm = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())
toks = [norm(w["w"]) for w in W]


def find(phrase, after_t=0.0):
    p = [norm(x) for x in phrase.split() if norm(x)]
    for i in range(len(W)):
        if W[i]["s"] >= after_t - 0.01 and toks[i:i + len(p)] == p:
            return i, i + len(p) - 1
    raise SystemExit(f"phrase not found after {after_t:.1f}s: {phrase!r} (check words_tl.json spelling, e.g. '815 ,000')")


out, cursor = [], 0.0
for g in G:
    if "a" in g:
        a, b = g["a"], g["b"]
    else:
        i0, i1 = find(g["start_phrase"], cursor)
        a = W[i0]["s"] - g.get("lead", 0.1)
        if g.get("end_phrase"):
            j0, j1 = find(g["end_phrase"], W[i1]["s"])
            b = W[j1]["e"] + 0.15
        else:
            b = a + g["file_dur"]
    speed = min(1.25, max(0.8, g["file_dur"] / (b - a)))
    if abs(speed - 1) < 0.005:
        speed = 1.0
    b = a + g["file_dur"] / speed
    out.append(dict(g, a=round(a, 3), b=round(b, 3), speed=round(speed, 4)))
    cursor = a + 0.5
    print(f"{a:8.2f}-{b:8.2f} x{speed:.3f}  {g['name']}")
cct.save(f"{work}/overlays.json", out)
```

### `overlays.py`
```python
"""Add motion graphics (+ subtle UI sounds) to the viewer's CURRENT CapCut draft, keeping their own edits,
and snap every graphic so no camera flash shows next to it.

usage: python3 overlays.py WORK_DIR CURRENT_PROJECT_COPY_DIR OUT_DIR
  WORK_DIR: overlays.json (from place_graphics.py), templates.json, sfx.json (optional), camera_16k.wav
  sfx.json: {"explainer": {"device": "/real/swipe.wav", "local": "staged copy"},
             "chapter":   {"device": "/real/swipe-ding.wav", "local": "staged copy", "use": 1.2},
             "level_db": -6.5}
Re-running replaces a graphics/SFX track an earlier run added (recognised by its file paths).
"""
import copy, hashlib, json, os, subprocess, sys, time
import numpy as np
import cct

work, proj, outd = sys.argv[1:4]
O = cct.load(f"{work}/overlays.json")
T = cct.load(f"{work}/templates.json")
SFX = cct.load(f"{work}/sfx.json") if os.path.exists(f"{work}/sfx.json") else None
name = next(n for n in ("draft_info.json", "draft_content.json") if os.path.exists(f"{proj}/{n}"))
D = cct.load(f"{proj}/{name}")
meta = cct.load(f"{proj}/draft_meta_info.json")
FPS = int(D.get("fps", 30))
us = lambda f: cct.us(f, FPS)
M = D["materials"]
allm = cct.all_materials(D)
TOTAL = D["duration"]

# drop graphics/SFX tracks a previous run added
gdev = {g["device"] for g in O}
sdev = {v["device"] for k, v in (SFX or {}).items() if isinstance(v, dict)}
def own(tr, devs):
    paths = [allm.get(s["material_id"], (None, {}))[1].get("path") for s in tr["segments"]]
    return paths and all(p in devs for p in paths)
D["tracks"] = [t for t in D["tracks"] if not own(t, gdev) and not own(t, sdev)]

# where the picture underneath changes: real camera cuts (not invisible same-source splits) + other overlays' edges
cuts = {0.0, TOTAL / 1e6}
main = D["tracks"][0]["segments"]
for p, s in zip(main, main[1:]):
    cont = (p["material_id"] != s["material_id"] and
            allm[p["material_id"]][1].get("path") == allm[s["material_id"]][1].get("path") and
            p["source_timerange"]["start"] + p["source_timerange"]["duration"] == s["source_timerange"]["start"])
    if not cont:
        cuts.add(s["target_timerange"]["start"] / 1e6)
for tr in D["tracks"][1:]:
    if tr["type"] == "video":
        for s in tr["segments"]:
            cuts.add(s["target_timerange"]["start"] / 1e6)
            cuts.add((s["target_timerange"]["start"] + s["target_timerange"]["duration"]) / 1e6)

items = [dict(g, max_dur=g["file_dur"] / 0.8) for g in O]
log = cct.snap_to_cuts(items, sorted(cuts))


def add(kind, tmpl, **kw):
    o = copy.deepcopy(tmpl)
    o["id"] = cct.U()
    o.update(kw)
    M.setdefault(kind, []).append(o)
    return o["id"]


def refs(pairs, speed=None, skip=()):
    return [add(k, o, **({"speed": float(speed)} if (k == "speeds" and speed is not None) else {}))
            for k, o in pairs if k not in skip]


gtrack = {"id": cct.U(), "type": "video", "flag": 2, "attribute": 0, "name": "", "is_default_name": True, "segments": []}
report, prev = [], 0
for g in sorted(items, key=lambda x: x["a"]):
    f0, f1 = cct.fr(g["a"], FPS), cct.fr(g["b"], FPS)
    file_us = us(cct.fr(g["file_dur"], FPS))
    need = file_us / (us(f1) - us(f0))                          # speed that plays the whole file in the slot
    speed = round(min(1.25, max(0.8, need)), 4)
    speed = 1.0 if abs(speed - 1) < 0.005 and abs(need - 1) < 0.005 else speed
    if need < 0.8:                                               # slot longer than the file can stretch
        f1 = f0 + int(file_us / 0.8 * FPS / 1e6)
    tl_us, dur_us = us(f0), us(f1) - us(f0)
    src_dur = min(int(round(dur_us * speed)), file_us)          # never read past the end of the file
    assert tl_us >= prev and tl_us + dur_us <= TOTAL, (g["name"], "overlaps or runs past the end")
    prev = tl_us + dur_us
    mid = add("videos", T["video_material"], path=g["device"], material_name=os.path.basename(g["device"]),
              width=g.get("w", 3840), height=g.get("h", 2160), duration=file_us, has_audio=False,
              unique_id="", local_material_id="", media_path="")
    s = copy.deepcopy(T["video_segment"])
    s.update({"id": cct.U(), "material_id": mid, "extra_material_refs": refs(T["video_refs"], speed=speed),
              "source_timerange": {"start": 0, "duration": src_dur}, "target_timerange": {"start": tl_us, "duration": dur_us},
              "speed": speed, "volume": 0.0, "last_nonzero_volume": 1.0, "keyframe_refs": [], "common_keyframes": []})
    s["clip"] = {"scale": {"x": 1.0, "y": 1.0}, "rotation": 0.0, "transform": {"x": 0.0, "y": 0.0},
                 "flip": {"vertical": False, "horizontal": False}, "alpha": 1.0}
    s["uniform_scale"] = {"on": True, "value": 1.0}
    gtrack["segments"].append(s)
    report.append({"name": g["name"], "start": tl_us / 1e6, "end": (tl_us + dur_us) / 1e6, "speed": speed,
                   "kind": g.get("kind", "explainer")})

# graphics sit directly above the last existing video overlay
last_video = max(i for i, t in enumerate(D["tracks"]) if t["type"] in ("video", "adjust"))
D["tracks"].insert(last_video + 1, gtrack)


def decode(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                         capture_output=True).stdout
    return np.frombuffer(raw, np.int16).astype(np.float32) / 32768


def st200(x):
    n = len(x) // 160
    r = (x[: n * 160].reshape(n, 160) ** 2).mean(1)
    return 10 * np.log10(np.convolve(r, np.ones(20) / 20, mode="same") + 1e-12)


if SFX:
    v = st200(decode(f"{work}/camera_16k.wav"))
    vo_med = float(np.median(v[v > v.max() - 30]))
    strack = {"id": cct.U(), "type": "audio", "flag": 0, "attribute": 0, "name": "", "is_default_name": True, "segments": []}
    prev = 0
    for r in report:
        cfg = SFX["chapter" if r["kind"] == "chapter" else "explainer"]
        x = decode(cfg["local"])
        st = st200(x)
        peak_t, dur = float(np.argmax(st)) / 100, len(x) / 16000
        vol = round(10 ** ((vo_med + SFX.get("level_db", -6.5) - float(st.max())) / 20), 4)
        tl_us = us(cct.fr(max(0.0, r["start"] - peak_t + 0.04), FPS))     # the swoosh peaks as the graphic cuts in
        tl_us = max(tl_us, prev)
        dur_us = min(us(cct.fr(cfg.get("use", dur), FPS)), int(dur * 1e6) - us(1))
        prev = tl_us + dur_us
        aid = add("audios", T["audio_material"], name=os.path.basename(cfg["device"]), path=cfg["device"],
                  duration=int(dur * 1e6), unique_id="", local_material_id="")
        s = copy.deepcopy(T["audio_segment"])
        s.update({"id": cct.U(), "material_id": aid, "extra_material_refs": refs(T["audio_refs"], speed=1.0, skip=("audio_fades",)),
                  "source_timerange": {"start": 0, "duration": dur_us}, "target_timerange": {"start": tl_us, "duration": dur_us},
                  "volume": vol, "last_nonzero_volume": 1.0, "speed": 1.0, "keyframe_refs": [], "common_keyframes": [],
                  "render_index": 0})
        strack["segments"].append(s)
    D["tracks"].append(strack)

for i, tr in enumerate(D["tracks"]):
    for s in tr["segments"]:
        s["track_render_index"] = i
for s in gtrack["segments"]:
    s["render_index"] = max([x.get("render_index", 0) for t in D["tracks"] if t is not gtrack for x in t["segments"]] + [0]) + 1
cct.validate(D)

os.makedirs(outd, exist_ok=True)
blob = json.dumps(D, ensure_ascii=False, separators=(",", ":"))
open(f"{outd}/{name}", "w", encoding="utf-8").write(blob)
meta["tm_draft_modified"] = int(time.time() * 1e6)
cct.save(f"{outd}/draft_meta_info.json", meta, compact=True)
md5 = hashlib.md5(blob.encode("utf-8")).hexdigest()
cct.save(f"{outd}/overlays_report.json", {"md5": md5, "graphics": report, "snaps": log})
print("tracks:", [(t["type"], t["flag"], len(t["segments"])) for t in D["tracks"]], "md5", md5)
for line in log:
    print("snap:", line)
for r in report:
    print(f"{r['start']:8.2f}-{r['end']:8.2f} x{r['speed']:<6} {r['name']}")
```

### `preview.py`
```python
"""Low-res preview MP4 of a CapCut draft, rendered from the draft itself (camera framing, cutaways, graphics,
music, sound effects; the grade is approximated).

usage: python3 preview.py DRAFT_INFO.json PATHMAP.json OUT.mp4 [--size 960x540]
  PATHMAP.json: {"<path in the draft>": "<local file to read: proxy or staged copy>", ...}
  Make 640x360 proxies on the viewer's computer first (fast), stage them, and map their real paths to them.
"""
import json, os, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
import cct

draft, pmap, out = sys.argv[1:4]
Wd, Hd = (int(x) for x in (sys.argv[sys.argv.index("--size") + 1] if "--size" in sys.argv else "960x540").split("x"))
D, P = cct.load(draft), cct.load(pmap)
M = cct.all_materials(D)
FPS = int(D.get("fps", 30))
tmp = os.path.join(os.path.dirname(os.path.abspath(out)), "_preview_tmp")
os.makedirs(tmp, exist_ok=True)
sec = lambda u: u / 1e6


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(" ".join(cmd[:12]) + " ...\n" + r.stderr[-1500:])


def local(seg):
    p = M[seg["material_id"]][1].get("path")
    if p not in P:
        raise SystemExit(f"no local file for {p}: add it to {pmap}")
    return P[p]


def scale_of(seg):
    for k in seg.get("common_keyframes") or []:
        if k["property_type"] == "KFTypeScaleX":
            v = [x["values"][0] for x in k["keyframe_list"]]
            return v[0], v[-1]
    s = seg["clip"]["scale"]["x"] if seg.get("clip") else 1.0
    return s, s


grade = {}
for tr in D["tracks"]:
    if tr["type"] == "adjust":
        for r in tr["segments"][0]["extra_material_refs"]:
            k, o = M.get(r, (None, {}))
            if k == "effects":
                grade[o.get("type")] = o.get("value", 0)
eq = f"eq=contrast={1 + grade.get('contrast', 0) * 0.8:.3f}:saturation={1 + grade.get('saturation', 0):.3f}"


def camera_clip(k, s):
    o = f"{tmp}/c{k:04d}.mp4"
    st, du = s["source_timerange"], s["target_timerange"]
    n = max(1, round(sec(du["duration"]) * FPS))
    s0, s1 = scale_of(s)
    vf = (f"scale={Wd * 2}:{Hd * 2},zoompan=z='{s0}+({s1}-{s0})*on/{max(1, n - 1)}':d=1:"
          f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={Wd}x{Hd}:fps={FPS},{eq},format=yuv420p")
    vol = s.get("volume", 1.0)
    run(["ffmpeg", "-v", "error", "-y", "-ss", f"{sec(st['start']):.4f}", "-i", local(s), "-frames:v", str(n),
         "-vf", vf, "-af", f"volume={vol},atrim=0:{n / FPS:.4f},apad", "-t", f"{n / FPS:.4f}", "-c:v", "libx264",
         "-preset", "veryfast", "-crf", "26", "-c:a", "aac", "-ar", "48000", "-ac", "2", o])
    return o


main = D["tracks"][0]["segments"]
with ThreadPoolExecutor(2) as ex:
    clips = list(ex.map(lambda a: camera_clip(*a), enumerate(main)))
open(f"{tmp}/list.txt", "w").write("".join(f"file '{c}'\n" for c in clips))
run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", f"{tmp}/list.txt", "-c", "copy", f"{tmp}/camera.mp4"])

inputs, fc, last = ["-i", f"{tmp}/camera.mp4"], [], "[0:v]"
alabels, n_in = ["[0:a]"], 1
for tr in D["tracks"][1:]:
    for s in tr["segments"]:
        if tr["type"] == "video":
            mat = M[s["material_id"]][1]
            st, du, sp = s["source_timerange"], s["target_timerange"], s.get("speed", 1.0)
            t0, d = sec(du["start"]), sec(du["duration"])
            if mat.get("type") == "photo":
                inputs += ["-loop", "1", "-t", f"{d + 0.1:.3f}", "-i", local(s)]
            else:
                inputs += ["-ss", f"{sec(st['start']):.3f}", "-t", f"{sec(st['duration']) + 0.1:.3f}", "-i", local(s)]
            sc = sum(scale_of(s)) / 2
            w = mat.get("width") or 1920
            h = mat.get("height") or 1080
            fit = min(Wd / w, Hd / h) * sc
            ow, oh = max(2, int(w * fit) // 2 * 2), max(2, int(h * fit) // 2 * 2)
            fc.append(f"[{n_in}:v]setpts=(PTS-STARTPTS)/{sp}+{t0:.3f}/TB,fps={FPS},scale={ow}:{oh}[o{n_in}]")
            fc.append(f"{last}[o{n_in}]overlay=x=(W-w)/2:y=(H-h)/2:eof_action=pass:"
                      f"enable='between(t,{t0:.3f},{t0 + d - 0.02:.3f})'[v{n_in}]")
            last = f"[v{n_in}]"
            n_in += 1
        elif tr["type"] == "audio":
            st, du = s["source_timerange"], s["target_timerange"]
            fin = fout = 0.0
            for r in s["extra_material_refs"]:
                k, o = M.get(r, (None, {}))
                if k == "audio_fades":
                    fin, fout = sec(o.get("fade_in_duration", 0)), sec(o.get("fade_out_duration", 0))
            d = sec(du["duration"])
            inputs += ["-ss", f"{sec(st['start']):.3f}", "-t", f"{d:.3f}", "-i", local(s)]
            f = f"[{n_in}:a]asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo,volume={s.get('volume', 1.0):.5f}"
            if fin:
                f += f",afade=t=in:st=0:d={fin:.2f}"
            if fout:
                f += f",afade=t=out:st={max(0, d - fout):.3f}:d={fout:.2f}"
            fc.append(f + f",adelay={int(sec(du['start']) * 1000)}:all=1[a{n_in}]")
            alabels.append(f"[a{n_in}]")
            n_in += 1
fc.append("".join(alabels) + f"amix=inputs={len(alabels)}:normalize=0:duration=first[a]")
vmap = last if last != "[0:v]" else "0:v"
run(["ffmpeg", "-v", "error", "-y"] + inputs + ["-filter_complex", ";".join(fc), "-map", vmap, "-map", "[a]",
     "-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", out])
print("preview ->", out)
```
