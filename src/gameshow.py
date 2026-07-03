"""Game-show wheel generator (build-time, pure Python).

A "spin the wheel" review game: the LLM (or an operator) supplies a list of
multiple-choice questions; each becomes one slice of a wheel. At play time the
learner spins, lands on a slice, and answers its question. Scored with PARTIAL
credit (correct / total), mirroring the other game blocks (wordSearch/crossword).

Like src/wordsearch.py and src/crossword.py this runs at course-BUILD time
(called from md_import): the interactive layout lives in the IR so the build is
self-contained and deterministic. Two pure things are computed here:

  * build() — normalises each question and DETERMINISTICALLY shuffles its options
    (correct answer + distractors) via a seeded LCG (no wall-clock / os.urandom),
    so a given course builds byte-identically every time and the correct-option
    index is fixed in the IR (the player never re-shuffles → resume-stable).

  * wheel_segments() — the SVG wedge geometry for an n-slice wheel. It is a pure
    function of the slice count, so render.py stays free of trig and the geometry
    is unit-testable without a DOM.

A question missing its stem, its correct answer, or every distractor is dropped
(a one-option "wheel" isn't a quiz); callers keep only the surviving slices.
"""
import math


class _Rng:
    """Tiny deterministic LCG — self-contained so behaviour can't drift with the
    stdlib `random` implementation. Numerical Recipes constants (mirrors
    wordsearch/crossword._Rng; kept independent so the generators can't couple)."""

    def __init__(self, seed):
        self._s = seed & 0xFFFFFFFF

    def _next(self):
        self._s = (1664525 * self._s + 1013904223) & 0xFFFFFFFF
        return self._s

    def shuffle(self, seq):
        for i in range(len(seq) - 1, 0, -1):
            j = self._next() % (i + 1)
            seq[i], seq[j] = seq[j], seq[i]


def _seed(parts):
    """FNV-1a hash of the question's text so option order is a pure function of
    content (same question → same shuffle), independent of position on the wheel."""
    key = "|".join(str(p) for p in parts)
    h = 2166136261
    for ch in key:
        h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    return h


def build(questions):
    """Normalise `questions` into wheel slices with deterministically-shuffled options.

    `questions` = [{"q": stem, "correct": answer, "distractors": [str, …]}, …].
    Returns {"slices": [{"q", "options": [str, …], "answer": <index>}, …], "n": N}.
    Options are de-duplicated case-insensitively (a distractor equal to the correct
    answer is dropped); a question with no stem, no correct answer, or no surviving
    distractor is dropped entirely. `answer` is the index of the correct option in
    the shuffled `options`, fixed here so the player never re-shuffles.
    """
    slices = []
    for item in questions or []:
        q = (item.get("q") or "").strip()
        correct = (item.get("correct") or "").strip()
        distractors = [str(d).strip() for d in (item.get("distractors") or []) if d and str(d).strip()]
        if not q or not correct:
            continue
        opts, seen = [], set()
        for o in [correct] + distractors:
            key = o.lower()
            if key in seen:
                continue
            seen.add(key)
            opts.append(o)
        if len(opts) < 2:          # need at least one real distractor to be a question
            continue
        order = list(range(len(opts)))
        _Rng(_seed([q, correct] + distractors)).shuffle(order)
        shuffled = [opts[j] for j in order]
        slices.append({"q": q, "options": shuffled, "answer": shuffled.index(correct)})
    return {"slices": slices, "n": len(slices)}


def wheel_segments(n, *, cx=100.0, cy=100.0, r=94.0, label_r=60.0):
    """Pure geometry for an n-slice wheel on a 200×200 canvas (centre 100,100).

    Returns a list (one per slice, in order) of
    {"d": <SVG path>, "mid": <deg>, "lx": <x>, "ly": <y>} where `d` is the wedge
    outline, `mid` is the clockwise angle of the slice CENTRE measured from the top
    (12 o'clock, where the pointer sits — so the player rotates the wheel by `-mid`
    to land a slice under the pointer), and (lx, ly) is the label anchor. A single
    slice is the whole disc. Coordinates are rounded to 2 dp so the SVG string is
    byte-identical across platforms. n <= 0 → [].
    """
    n = int(n)
    if n <= 0:
        return []

    def pt(angle_deg, radius):
        # 0deg = top (12 o'clock); increasing clockwise.
        a = math.radians(angle_deg - 90.0)
        return (round(cx + radius * math.cos(a), 2), round(cy + radius * math.sin(a), 2))

    if n == 1:
        top = pt(0, r)
        bot = pt(180, r)
        d = ("M{tx},{ty} A{r},{r} 0 1 1 {bx},{by} A{r},{r} 0 1 1 {tx},{ty} Z"
             .format(tx=top[0], ty=top[1], bx=bot[0], by=bot[1], r=r))
        return [{"d": d, "mid": 0.0, "lx": round(cx, 2), "ly": round(cy, 2)}]

    step = 360.0 / n
    out = []
    for i in range(n):
        a0, a1 = i * step, (i + 1) * step
        x0, y0 = pt(a0, r)
        x1, y1 = pt(a1, r)
        large = 1 if step > 180.0 else 0
        d = ("M{cx},{cy} L{x0},{y0} A{r},{r} 0 {lg} 1 {x1},{y1} Z"
             .format(cx=round(cx, 2), cy=round(cy, 2), x0=x0, y0=y0, x1=x1, y1=y1, r=r, lg=large))
        mid = (i + 0.5) * step
        lx, ly = pt(mid, label_r)
        out.append({"d": d, "mid": round(mid, 2), "lx": lx, "ly": ly})
    return out
