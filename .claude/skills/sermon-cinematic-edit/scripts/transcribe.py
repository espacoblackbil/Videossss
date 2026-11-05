"""Portuguese transcript with word timings (large-v3-turbo), for captions and quote cards.

usage: HF_HUB_DISABLE_XET=1 python3 transcribe.py WORK [--model mobiuslabsgmbh/faster-whisper-large-v3-turbo]
  needs WORK/camera_16k.wav; writes WORK/words_turbo.json and prints the lines.
Whisper repeats a phrase over and over at the very end of a file when the voice stops: those repeats are dropped.
"""
import json, sys, wave
import numpy as np
from faster_whisper import WhisperModel

work = sys.argv[1]
model = sys.argv[sys.argv.index("--model") + 1] if "--model" in sys.argv else "mobiuslabsgmbh/faster-whisper-large-v3-turbo"
wf = wave.open(f"{work}/camera_16k.wav")
a = np.frombuffer(wf.readframes(wf.getnframes()), np.int16).astype(np.float32) / 32768
m = WhisperModel(model, device="cpu", compute_type="int8")
segs, _ = m.transcribe(a, language="pt", word_timestamps=True, beam_size=5, temperature=0)
words, seen = [], set()
for s in segs:
    key = s.text.strip().lower()
    if key in seen and s.end - s.start < 1.0:      # end-of-file hallucination loop
        continue
    seen.add(key)
    print(f"{s.start:6.2f} {s.text.strip()}")
    for w in s.words:
        words.append({"w": w.word.strip(), "s": round(w.start, 3), "e": round(w.end, 3)})
json.dump(words, open(f"{work}/words_turbo.json", "w"), ensure_ascii=False)
print(len(words), "words")
