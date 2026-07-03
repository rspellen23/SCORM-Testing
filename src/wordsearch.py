"""Word-search grid generator (build-time, pure Python).

Ports the core placement idea of bunkat/wordfind (MIT) into dependency-free
Python. The generator runs at course-BUILD time (called from md_import): the LLM
(or an operator) supplies only a list of terms, and this turns them into a
finished letter grid. The player never generates anything — it just renders the
grid and scores the words the learner finds. Placements are kept in the IR for
verification / a future "reveal answers" feature; the player does not need them.

Determinism: output is a pure function of (words, size) via a seeded RNG, so a
given course builds byte-identically every time and tests are stable. No
wall-clock / os.urandom seeding.
"""
import math
import re

# 8 compass directions as (dr, dc). The "forward" set is the default; `reverse`
# adds the mirrored directions (words can then run right→left / bottom→top).
_DIRS_FWD = {"E": (0, 1), "S": (1, 0), "SE": (1, 1), "NE": (-1, 1)}
_DIRS_REV = {"W": (0, -1), "N": (-1, 0), "SW": (1, -1), "NW": (-1, -1)}
_ORTHO = {"E": (0, 1), "S": (1, 0)}
_ORTHO_REV = {"W": (0, -1), "N": (-1, 0)}
_ALPHA = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def clean_word(word):
    """Uppercase, strip everything that isn't A–Z (spaces, punctuation, digits)."""
    return re.sub(r"[^A-Z]", "", str(word or "").upper())


class _Rng:
    """Tiny deterministic LCG — self-contained so behavior can't drift with the
    stdlib `random` implementation. Numerical Recipes constants."""

    def __init__(self, seed):
        self._s = seed & 0xFFFFFFFF

    def _next(self):
        self._s = (1664525 * self._s + 1013904223) & 0xFFFFFFFF
        return self._s

    def randrange(self, n):
        return self._next() % n if n > 0 else 0

    def shuffle(self, seq):
        for i in range(len(seq) - 1, 0, -1):
            j = self._next() % (i + 1)
            seq[i], seq[j] = seq[j], seq[i]


def _seed(words, size):
    key = "|".join(sorted(words)) + "#" + str(size)
    h = 2166136261
    for ch in key:
        h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    return h


def _dirs(diagonal, reverse):
    d = dict(_DIRS_FWD if diagonal else _ORTHO)
    if reverse:
        d.update(_DIRS_REV if diagonal else _ORTHO_REV)
    return d


def _try_place(words, size, dirs, rng):
    """Place every word or fail (return None). For each word, enumerate every
    legal (position × direction) whose cells are empty or already carry the same
    letter, shuffle, and take the first. Longest words are placed first (caller)."""
    grid = [[None] * size for _ in range(size)]
    placements = []
    dir_items = list(dirs.items())
    for w in words:
        spots = []
        n = len(w)
        for name, (dr, dc) in dir_items:
            for r in range(size):
                er = r + dr * (n - 1)
                if er < 0 or er >= size:
                    continue
                for c in range(size):
                    ec = c + dc * (n - 1)
                    if ec < 0 or ec >= size:
                        continue
                    ok = True
                    for k in range(n):
                        cell = grid[r + dr * k][c + dc * k]
                        if cell is not None and cell != w[k]:
                            ok = False
                            break
                    if ok:
                        spots.append((r, c, dr, dc, name))
        if not spots:
            return None
        rng.shuffle(spots)
        r, c, dr, dc, name = spots[0]
        for k in range(n):
            grid[r + dr * k][c + dc * k] = w[k]
        placements.append({"text": w, "r": r, "c": c, "dr": dr, "dc": dc, "dir": name})
    return grid, placements


def _fill(grid, size, rng):
    for r in range(size):
        for c in range(size):
            if grid[r][c] is None:
                grid[r][c] = _ALPHA[rng.randrange(26)]


def generate(words, *, size=None, diagonal=True, reverse=False, max_grow=8):
    """Build a word-search from `words`.

    Returns {"grid": [[ch,…],…], "words": [{text,r,c,dr,dc,dir},…], "size": N}.
    Empty/short (<2-letter) and duplicate words are dropped. If placement fails on
    the chosen size the grid grows one row/col at a time (up to `max_grow`); as a
    last resort it retries orthogonal-only on a generous grid so a valid grid is
    (almost) always returned. `words` in → same grid out (deterministic).
    """
    cleaned, seen = [], set()
    for w in words:
        c = clean_word(w)
        if len(c) >= 2 and c not in seen:
            seen.add(c)
            cleaned.append(c)
    if not cleaned:
        return {"grid": [], "words": [], "size": 0}

    # Place the longest words first (they are the hardest to fit).
    ordered = sorted(cleaned, key=lambda w: (-len(w), w))
    longest = len(ordered[0])
    total = sum(len(w) for w in ordered)
    if size is None:
        # Enough room for the longest word, plus slack scaled to the letter count.
        size = max(longest, int(math.ceil(math.sqrt(total * 1.6))) + 1)
    size = max(size, longest)

    rng = _Rng(_seed(cleaned, size))
    dirs = _dirs(diagonal, reverse)
    cur = size
    for _ in range(max_grow):
        res = _try_place(ordered, cur, dirs, rng)
        if res is not None:
            grid, placements = res
            _fill(grid, cur, rng)
            return {"grid": grid, "words": _order_like(placements, cleaned), "size": cur}
        cur += 1
    # Fallback: orthogonal-only on a roomy grid (each word on its own row is always feasible).
    cur = max(cur, longest, len(ordered) + 1)
    res = _try_place(ordered, cur, _dirs(False, reverse), rng)
    grid, placements = res if res is not None else ([[_ALPHA[0]] * cur for _ in range(cur)], [])
    _fill(grid, cur, rng)
    return {"grid": grid, "words": _order_like(placements, cleaned), "size": cur}


def _order_like(placements, order):
    """Return placements in the authored order (not longest-first placement order)."""
    by_text = {p["text"]: p for p in placements}
    return [by_text[w] for w in order if w in by_text]
