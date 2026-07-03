"""Crossword layout generator (build-time, pure Python).

Reimplements the classic greedy interlocking-crossword algorithm (the approach
popularised by MichaelWehar/Crossword-Layout-Generator, MIT) into dependency-free
Python. Like src/wordsearch.py, it runs at course-BUILD time (called from
md_import): the LLM (or an operator) supplies only a list of answers (each with a
clue); this interlocks them into a numbered grid. The player never generates
anything — it renders the grid + clue lists and scores the words the learner
types in. Placements/numbering are computed here so the build is self-contained.

Determinism: output is a pure function of the input words via a seeded RNG (no
wall-clock / os.urandom), so a given course builds byte-identically every time
and tests are stable.

A word that cannot be interlocked with the others is DROPPED (a crossword needs
crossings); callers keep only the placed words' clues. With the 5–10 related
terms a vocabulary crossword uses, that essentially never happens, but the
generator tries several orderings and keeps the layout that places the most.
"""
import re

_ACROSS = "across"
_DOWN = "down"


def clean_word(word):
    """Uppercase, strip everything that isn't A–Z (spaces, punctuation, digits)."""
    return re.sub(r"[^A-Z]", "", str(word or "").upper())


class _Rng:
    """Tiny deterministic LCG — self-contained so behavior can't drift with the
    stdlib `random` implementation. Numerical Recipes constants (mirrors
    wordsearch._Rng; kept independent so the two generators can't couple)."""

    def __init__(self, seed):
        self._s = seed & 0xFFFFFFFF

    def _next(self):
        self._s = (1664525 * self._s + 1013904223) & 0xFFFFFFFF
        return self._s

    def shuffle(self, seq):
        for i in range(len(seq) - 1, 0, -1):
            j = self._next() % (i + 1)
            seq[i], seq[j] = seq[j], seq[i]


def _seed(words, salt):
    key = "|".join(sorted(words)) + "#" + str(salt)
    h = 2166136261
    for ch in key:
        h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    return h


def _place_first(word):
    """Seed the layout with the first (longest) word laid across at the origin."""
    cells = {}
    for j, ch in enumerate(word):
        cells[(0, j)] = ch
    return cells, [{"text": word, "r": 0, "c": 0, "dir": _ACROSS}]


def _fits(cells, word, r0, c0, dr, dc):
    """Return the crossing count if `word` can be laid from (r0,c0) stepping
    (dr,dc), else None. A legal placement: every overlapped cell already holds
    the SAME letter (a real crossing); every fresh cell's perpendicular neighbours
    are empty (no accidental parallel words); and the cells just before the start
    and just after the end are empty (no run-on into another word)."""
    n = len(word)
    crossings = 0
    # A cell before the start / after the end would extend an existing word.
    if (r0 - dr, c0 - dc) in cells or (r0 + dr * n, c0 + dc * n) in cells:
        return None
    for j, ch in enumerate(word):
        rr, cc = r0 + dr * j, c0 + dc * j
        here = cells.get((rr, cc))
        if here is not None:
            if here != ch:
                return None
            crossings += 1
        else:
            # Perpendicular neighbours of a NEW cell must be empty. (Stepping
            # direction is (dr,dc); the perpendicular is (dc,dr).)
            if (rr + dc, cc + dr) in cells or (rr - dc, cc - dr) in cells:
                return None
    return crossings


def _candidates(cells, word):
    """Every legal placement of `word` that crosses the current layout, as
    (crossings, r0, c0, dir). Enumerated by matching each of the word's letters
    against every occupied cell of the opposite orientation."""
    out = []
    for (pr, pc), letter in cells.items():
        for k, ch in enumerate(word):
            if ch != letter:
                continue
            # Try the word DOWN through this cell, and ACROSS through this cell.
            for dr, dc, name in ((1, 0, _DOWN), (0, 1, _ACROSS)):
                r0, c0 = pr - dr * k, pc - dc * k
                cr = _fits(cells, word, r0, c0, dr, dc)
                if cr:  # crossings >= 1 (an interlocking placement)
                    out.append((cr, r0, c0, name))
    return out


def _build(order, rng):
    """Greedily interlock `order` (a placement order, longest-ish first). Returns
    a placements list + the occupied-cell map."""
    if not order:
        return [], {}
    cells, placements = _place_first(order[0])
    for word in order[1:]:
        cand = _candidates(cells, word)
        if not cand:
            continue  # can't interlock this word — drop it
        # Prefer the most crossings; shuffle first so ties break with variety
        # across seeds, then pick the max deterministically.
        rng.shuffle(cand)
        best = max(cand, key=lambda x: x[0])
        _cr, r0, c0, name = best
        dr, dc = (1, 0) if name == _DOWN else (0, 1)
        for j, ch in enumerate(word):
            cells[(r0 + dr * j, c0 + dc * j)] = ch
        placements.append({"text": word, "r": r0, "c": c0, "dir": name})
    return placements, cells


def _normalize(placements, cells):
    """Shift so the top-left of the bounding box is (0,0); return (grid, rows, cols)
    with the placements mutated in place to the new coordinates. Blocked cells are
    None."""
    if not cells:
        return [], 0, 0
    minr = min(r for r, _ in cells)
    minc = min(c for _, c in cells)
    maxr = max(r for r, _ in cells)
    maxc = max(c for _, c in cells)
    rows, cols = maxr - minr + 1, maxc - minc + 1
    grid = [[None] * cols for _ in range(rows)]
    for (r, c), ch in cells.items():
        grid[r - minr][c - minc] = ch
    for p in placements:
        p["r"] -= minr
        p["c"] -= minc
    return grid, rows, cols


def _number(grid, rows, cols, placements):
    """Assign crossword numbers: scan row-major; a white cell starts a number when
    it begins an across run (no white cell to its left, a white cell to its right)
    and/or a down run (none above, one below). Stamp each placement with the number
    of its start cell (an across + down sharing a start cell share the number)."""
    def white(r, c):
        return 0 <= r < rows and 0 <= c < cols and grid[r][c] is not None

    num_at = {}
    n = 0
    for r in range(rows):
        for c in range(cols):
            if not white(r, c):
                continue
            starts_across = white(r, c + 1) and not white(r, c - 1)
            starts_down = white(r + 1, c) and not white(r - 1, c)
            if starts_across or starts_down:
                n += 1
                num_at[(r, c)] = n
    for p in placements:
        p["num"] = num_at.get((p["r"], p["c"]), 0)


def generate(words, *, tries=8):
    """Build an interlocking crossword from `words`.

    Returns {"grid": [[ch|None,…],…], "words": [{text,r,c,dir,num},…],
    "rows": R, "cols": C}. Empty/short (<2-letter) and duplicate words are dropped
    before layout; a word that cannot interlock is dropped during layout. Tries
    several deterministic orderings and keeps the one placing the most words (ties:
    smallest area). `words` in → same layout out.
    """
    cleaned, seen = [], set()
    for w in words:
        c = clean_word(w)
        if len(c) >= 2 and c not in seen:
            seen.add(c)
            cleaned.append(c)
    if not cleaned:
        return {"grid": [], "words": [], "rows": 0, "cols": 0}

    base = sorted(cleaned, key=lambda w: (-len(w), w))  # longest first is easiest to interlock
    best = None
    for t in range(max(1, tries)):
        order = base[:]
        rng = _Rng(_seed(cleaned, t))
        if t > 0:
            # Shuffle the tail but keep the longest word leading the placement.
            tail = order[1:]
            rng.shuffle(tail)
            order = order[:1] + tail
        placements, cells = _build(order, rng)
        grid, rows, cols = _normalize(placements, cells)
        # Reorder placements back into the AUTHORED order (not the longest-first
        # placement order) so the result is stable regardless of which try won.
        placements = _order_like(placements, cleaned)
        _number(grid, rows, cols, placements)
        score = (len(placements), -(rows * cols))
        if best is None or score > best[0]:
            best = (score, grid, rows, cols, placements)
    _score, grid, rows, cols, placements = best
    return {"grid": grid, "words": placements, "rows": rows, "cols": cols}


def _order_like(placements, order):
    """Return placements in the authored order (not placement order)."""
    by_text = {p["text"]: p for p in placements}
    return [by_text[w] for w in order if w in by_text]
