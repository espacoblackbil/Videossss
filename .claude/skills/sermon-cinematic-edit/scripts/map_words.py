"""Put every spoken word on the FINAL timeline (after cuts and speed), with an optional hand-corrected text.

usage: python3 map_words.py WORK [--speed 1.3] [--words words_turbo.json] [--text corrected.txt]
  WORK needs edl.json (from edl.py) and a word list [{"w","s","e"}] in source seconds.
  corrected.txt: the full transcript, fixed and punctuated by hand, with EXACTLY one token per transcribed word
                 (merge "amá -lo" style splits in the word list first). The script refuses a count mismatch and
                 prints which words changed, so a wrong correction is visible.
writes WORK/words_final.json: [{"w", "a", "b"}] in final-video seconds.
"""
import json, re, sys

work = sys.argv[1]
arg = lambda k, d: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d
SPEED = float(arg("--speed", "1.0"))
E = json.load(open(f"{work}/edl.json"))
FPS = E["fps"]
T = json.load(open(f"{work}/{arg('--words', 'words_turbo.json')}"))
T = [w for w in T if w["w"].strip()]
txt = arg("--text", None)
if txt:
    toks = open(txt, encoding="utf-8").read().split()
    assert len(toks) == len(T), f"corrected text has {len(toks)} tokens, transcript has {len(T)}"
    norm = lambda s: re.sub(r"[^\w-]", "", s.lower())
    print("changed:", [(T[k]["w"], t) for k, t in enumerate(toks) if norm(T[k]["w"]) != norm(t)])
    for k, t in enumerate(toks):
        T[k]["w"] = t


def to_tl(t):
    f = t * FPS
    for c in E["clips"]:
        if c["src0"] <= f < c["src1"]:
            return (c["tl0"] + f - c["src0"]) / FPS / SPEED
    for c in E["clips"]:
        if c["src0"] > f:
            return c["tl0"] / FPS / SPEED
    return E["total_frames"] / FPS / SPEED


out = [{"w": w["w"].strip(), "a": round(to_tl(w["s"]), 3), "b": round(to_tl(w["e"]), 3)} for w in T]
json.dump(out, open(f"{work}/words_final.json", "w"), ensure_ascii=False)
print(len(out), "words ->", f"{work}/words_final.json")
