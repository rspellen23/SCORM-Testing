/*
 * Player runtime regression tests (C3) — run with `node --test`.
 *
 * player/player.js had ZERO committed tests; the 2026-06-23 hardening and the
 * multi-select knowledge-check scoring were verified only by throwaway scripts.
 * The pure decision logic (multi-select correctness, the retry/lock gate, graded
 * scoring, the suspend_data byte-budget ladder, and the packed-rung resume parse)
 * is now exported from player.js and pinned here so a future edit can't silently
 * re-open the scoring or the suspend-truncation bug with the suite still green.
 *
 * The DOM bootstrap in player.js is HAS_DOM-guarded, so requiring it under node
 * defines + exports the helpers without touching window/document.
 */
const { test } = require("node:test");
const assert = require("node:assert/strict");

const P = require("../player/player.js");

// --------------------------------------------------------------- multi-select scoring

test("multi-select is correct only when every right option is picked and no wrong one", () => {
  const corrects = [true, false, true];        // options 0 and 2 are the answers
  // all-correct, none-wrong
  assert.equal(P.multiAllCorrect(corrects, [0, 2]), true);
  assert.equal(P.multiAllCorrect(corrects, [2, 0]), true);   // order-independent
  // partial: a right answer missing
  assert.equal(P.multiAllCorrect(corrects, [0]), false);
  // a wrong option included (even with both right ones)
  assert.equal(P.multiAllCorrect(corrects, [0, 1, 2]), false);
  // only a wrong option
  assert.equal(P.multiAllCorrect(corrects, [1]), false);
  // empty selection never scores (the UI blocks it; the logic agrees)
  assert.equal(P.multiAllCorrect(corrects, []), false);
});

test("a single-correct KC behaves as a degenerate multi-select", () => {
  const corrects = [false, true, false];
  assert.equal(P.multiAllCorrect(corrects, [1]), true);
  assert.equal(P.multiAllCorrect(corrects, [0]), false);
  assert.equal(P.multiAllCorrect(corrects, [1, 2]), false);
});

// --------------------------------------------------------------- retry / lock gate

test("one-shot KC always locks (right or wrong)", () => {
  assert.equal(P.kcLocks(true, 1, 0), true);
  assert.equal(P.kcLocks(false, 1, 0), true);     // maxTries=0 => no retry
});

test("graded retry holds a wrong answer until the last attempt, then locks", () => {
  const maxTries = 3;
  assert.equal(P.kcLocks(false, 1, maxTries), false);   // wrong, attempts left -> retry
  assert.equal(P.kcLocks(false, 2, maxTries), false);   // still attempts left
  assert.equal(P.kcLocks(false, 3, maxTries), true);    // last attempt used -> lock
  assert.equal(P.kcLocks(true, 1, maxTries), true);     // correct always locks immediately
});

test("graded quiz: fail then retry-to-pass crosses the mastery threshold", () => {
  const passMark = 80;
  // 2-KC quiz: first attempt gets 1/2 right -> 50% -> fails (must hold completion)
  assert.equal(P.scorePct(1, 2), 50);
  assert.equal(P.scorePct(1, 2) >= passMark, false);
  // after retry the learner gets 2/2 -> 100% -> passes
  assert.equal(P.scorePct(2, 2), 100);
  assert.equal(P.scorePct(2, 2) >= passMark, true);
  // no KCs -> 0%, never a divide-by-zero
  assert.equal(P.scorePct(0, 0), 0);
});

// --------------------------------------------------------------- suspend round-trip + packed rung

test("fitSuspend keeps the full {opt,multi} KC rung when it fits the byte budget", () => {
  const state = { g: [0], k: { "0": { opt: "0,2", ok: 1, multi: 1 } },
                  m: [], o: [], s: {}, loc: { t: "kc", i: 0 } };
  const packed = P.fitSuspend(state);
  const round = JSON.parse(packed);            // never a truncated blob
  assert.deepEqual(round.k["0"], { opt: "0,2", ok: 1, multi: 1 });
  // and that rung resumes to the right option indexes
  assert.deepEqual(P.parseMultiSel(round.k["0"].opt), [0, 2]);
});

test("fitSuspend degrades an over-budget course to the packed rung (keeps ok, drops detail)", () => {
  // build a KC set far larger than the ~4000-byte 1.2 budget so the ladder must
  // fall through to packKcs — the rung that keeps only correctness.
  const k = {};
  for (let i = 0; i < 200; i++) k[String(i)] = { opt: "0,1,2,3", ok: i % 2, multi: 1 };
  const state = { g: [], k, m: [], o: [], s: {}, loc: { t: "kc", i: 199 } };
  assert.ok(P.utf8len(JSON.stringify(state)) > 4096, "fixture must overflow the budget");
  const out = P.fitSuspend(state);
  assert.ok(P.utf8len(out) <= 4096, "must fit the SCORM 1.2 suspend_data budget");
  const round = JSON.parse(out);               // still valid JSON, not truncated
  assert.equal("loc" in round, false, "cosmetic resume pointer dropped first");
  // every rung is packed to just {ok}; option detail is gone but correctness survives
  assert.deepEqual(round.k["1"], { ok: 1 });
  assert.deepEqual(round.k["2"], { ok: 0 });
});

test("packKcs/packSorts keep correctness, drop per-item detail", () => {
  assert.deepEqual(P.packKcs({ "0": { opt: "0,2", ok: 1, multi: 1 }, "1": { opt: 3, ok: 0 } }),
    { "0": { ok: 1 }, "1": { ok: 0 } });
  assert.deepEqual(P.packSorts({ s0: { picks: [1, 0], ok: 1 } }), { s0: { ok: 1 } });
});

// --------------------------------------------------------------- packed-rung resume parse

test("parseMultiSel restores a full rung and tolerates a packed/empty one", () => {
  assert.deepEqual(P.parseMultiSel("0,2"), [0, 2]);
  assert.deepEqual(P.parseMultiSel("1"), [1]);
  assert.deepEqual(P.parseMultiSel(""), []);       // packed rung lost its opt -> no picks
  assert.deepEqual(P.parseMultiSel(3), [3]);        // numeric opt coerces cleanly
});

// --------------------------------------------------------------- utf8 byte measurement

test("utf8len measures real UTF-8 bytes, not UTF-16 code units", () => {
  assert.equal(P.utf8len("abc"), 3);
  assert.equal(P.utf8len("é"), 2);                  // 2-byte
  assert.equal(P.utf8len("€"), 3);                  // 3-byte
  assert.equal(P.utf8len("😀"), 4);                 // surrogate pair -> 4 bytes
});
