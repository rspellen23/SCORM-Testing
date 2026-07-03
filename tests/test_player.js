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

test("fitSuspend carries dragDrop (dd) state and packs it like the other partial blocks", () => {
  // dragDrop rides the same suspend ladder as matching/sequence/fill: the full rung keeps
  // per-label picks; the packed rung drops picks but keeps {ok,got,max} so the score survives.
  const state = { g: [], k: {}, m: [], o: [], s: {}, mt: {}, sq: {}, fl: {},
                  dd: { dd0: { ok: 0, got: 1, max: 2, picks: ["z1", ""] } }, loc: { t: "dd", i: 0 } };
  const round = JSON.parse(P.fitSuspend(state));
  // small course → full rung: dd present with its picks intact
  assert.deepEqual(round.dd.dd0, { ok: 0, got: 1, max: 2, picks: ["z1", ""] });
  // and under byte pressure packSeen drops the picks but keeps the graded fields
  assert.deepEqual(P.packSeen(state.dd), { dd0: { ok: 0, got: 1, max: 2 } });
});

test("fitSuspend carries wordSearch (ws) state and packs it like the other partial blocks", () => {
  // wordSearch rides the same suspend ladder: the full rung keeps the found-word list;
  // the packed rung drops `found` but keeps {ok,got,max} so the partial score survives.
  const state = { g: [], k: {}, m: [], o: [], s: {}, mt: {}, sq: {}, fl: {}, dd: {},
                  ws: { ws0: { ok: 0, got: 2, max: 3, found: ["CURSOR", "SUITE"] } }, loc: { t: "ws", i: 0 } };
  const round = JSON.parse(P.fitSuspend(state));
  assert.deepEqual(round.ws.ws0, { ok: 0, got: 2, max: 3, found: ["CURSOR", "SUITE"] });
  assert.deepEqual(P.packSeen(state.ws), { ws0: { ok: 0, got: 2, max: 3 } });
});

test("fitSuspend carries crossword (cw) state and packs it like the other partial blocks", () => {
  // crossword rides the same suspend ladder: the full rung keeps the typed-letter map;
  // the packed rung drops `letters` but keeps {ok,got,max} so the partial score survives.
  const state = { g: [], k: {}, m: [], o: [], s: {}, mt: {}, sq: {}, fl: {}, dd: {}, ws: {},
                  cw: { cw0: { ok: 0, got: 1, max: 2, letters: { "0,0": "D", "1,0": "H" } } },
                  loc: { t: "cw", i: 0 } };
  const round = JSON.parse(P.fitSuspend(state));
  assert.deepEqual(round.cw.cw0, { ok: 0, got: 1, max: 2, letters: { "0,0": "D", "1,0": "H" } });
  assert.deepEqual(P.packSeen(state.cw), { cw0: { ok: 0, got: 1, max: 2 } });
});

test("fitSuspend carries gameShow (gs) state and packs it like the other partial blocks", () => {
  // gameShow registers one entry per block once every slice is answered; the full rung keeps the
  // per-slice correctness map `ans`, the packed rung drops it but keeps {ok,got,max} for the score.
  const state = { g: [], k: {}, m: [], o: [], s: {}, mt: {}, sq: {}, fl: {}, dd: {}, ws: {}, cw: {},
                  gs: { gs0: { ok: 0, got: 2, max: 3, ans: { 0: 1, 1: 0, 2: 1 } } },
                  loc: { t: "gs", i: 0 } };
  const round = JSON.parse(P.fitSuspend(state));
  assert.deepEqual(round.gs.gs0, { ok: 0, got: 2, max: 3, ans: { 0: 1, 1: 0, 2: 1 } });
  assert.deepEqual(P.packSeen(state.gs), { gs0: { ok: 0, got: 2, max: 3 } });
});

test("fitSuspend carries quizBoard (qb) state and packs it like the other partial blocks", () => {
  // quizBoard registers one entry per board once every tile is answered; got/max are WEIGHTED by
  // point value (not a tile count), so the packed rung must keep them for the score, dropping `ans`.
  const state = { g: [], k: {}, m: [], o: [], s: {}, mt: {}, sq: {}, fl: {}, dd: {}, ws: {}, cw: {}, gs: {},
                  qb: { qb0: { ok: 0, got: 300, max: 600, ans: { 0: 1, 1: 0, 2: 1, 3: 0 } } },
                  loc: { t: "qb", i: 0 } };
  const round = JSON.parse(P.fitSuspend(state));
  assert.deepEqual(round.qb.qb0, { ok: 0, got: 300, max: 600, ans: { 0: 1, 1: 0, 2: 1, 3: 0 } });
  assert.deepEqual(P.packSeen(state.qb), { qb0: { ok: 0, got: 300, max: 600 } });
});

test("fitSuspend carries speedStreak (ss) state and packs it like the other partial blocks", () => {
  // speedStreak registers one entry per block once every round is answered; the full rung keeps the
  // per-round correctness map `ans`, the packed rung drops it but keeps {ok,got,max} for the score.
  const state = { g: [], k: {}, m: [], o: [], s: {}, mt: {}, sq: {}, fl: {}, dd: {}, ws: {}, cw: {}, gs: {}, qb: {},
                  ss: { ss0: { ok: 0, got: 2, max: 3, ans: { 0: 1, 1: 0, 2: 1 } } },
                  loc: { t: "ss", i: 0 } };
  const round = JSON.parse(P.fitSuspend(state));
  assert.deepEqual(round.ss.ss0, { ok: 0, got: 2, max: 3, ans: { 0: 1, 1: 0, 2: 1 } });
  assert.deepEqual(P.packSeen(state.ss), { ss0: { ok: 0, got: 2, max: 3 } });
});

test("fitSuspend carries reflection (rf) state; packing drops the typed text but keeps completion", () => {
  // C7 reflection is non-graded, completion-only. The full rung keeps the learner's typed text so a
  // resume is faithful; under byte pressure packSeen drops the text and keeps only the completion flag
  // (the model answer + rubric live in the DOM and are re-revealed on resume regardless).
  const state = { g: [], k: {}, m: [], o: [], s: {}, mt: {}, sq: {}, fl: {}, dd: {}, ws: {}, cw: {}, gs: {}, qb: {}, ss: {},
                  rf: { rf0: { ok: 1, text: "I would call the on-call coordinator first.", rev: 1 } },
                  loc: { t: "rf", i: 0 } };
  const round = JSON.parse(P.fitSuspend(state));
  assert.deepEqual(round.rf.rf0, { ok: 1, text: "I would call the on-call coordinator first.", rev: 1 });
  assert.deepEqual(JSON.parse(JSON.stringify(P.packSeen(state.rf))), { rf0: { ok: 1 } });
});

test("ssScore grades a speedStreak by correct count (all-correct → ok), independent of streak/timer", () => {
  assert.deepEqual(P.ssScore([true, true, true]), { got: 3, max: 3, ok: true });
  assert.deepEqual(P.ssScore([true, false, true]), { got: 2, max: 3, ok: false });
  assert.deepEqual(P.ssScore([]), { got: 0, max: 0, ok: false });
});

test("ssCombo is a cosmetic streak/speed multiplier (a wrong answer scores 0, never negative)", () => {
  assert.equal(P.ssCombo(false, 5, 1), 0);        // wrong → 0 regardless of streak/time
  assert.equal(P.ssCombo(true, 0, 0), 100);       // first correct, no streak, no time bonus → base
  assert.equal(P.ssCombo(true, 2, 0), 200);       // streak of 2 → ×(1 + 0.5·2) = ×2
  assert.equal(P.ssCombo(true, 0, 1), 200);       // full clock remaining → ×(1 + 1) speed bonus
  assert.equal(P.ssCombo(true, 2, 1), 400);       // streak ×2 AND full speed bonus ×2
  assert.ok(P.ssCombo(true, 0, 0) >= 0);          // never negative
});

test("celebrateAllowed gates confetti by config + once-guard (pass/complete once, level recurs)", () => {
  const all = { pass: true, level: true, complete: true };
  // one-shot triggers: allowed only while not yet fired
  assert.equal(P.celebrateAllowed(all, "pass", false), true);
  assert.equal(P.celebrateAllowed(all, "pass", true), false);      // already fired → no repeat
  assert.equal(P.celebrateAllowed(all, "complete", false), true);
  assert.equal(P.celebrateAllowed(all, "complete", true), false);
  // level-up recurs — the `fired` arg is ignored (each tier crossing is genuine)
  assert.equal(P.celebrateAllowed(all, "level", false), true);
  assert.equal(P.celebrateAllowed(all, "level", true), true);
  // a disabled trigger never fires; no config at all never fires
  assert.equal(P.celebrateAllowed({ pass: false, level: true, complete: true }, "pass", false), false);
  assert.equal(P.celebrateAllowed(null, "complete", false), false);
  assert.equal(P.celebrateAllowed(all, "bogus", false), false);    // unknown reason → no
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

// --------------------------------------------------------------- scenario branching (M14)

test("resolveScene routes a goto to its scene index", () => {
  const ids = ["start", "escalated", "waited"];
  assert.equal(P.resolveScene("escalated", ids), 1);   // routes to the named scene
  assert.equal(P.resolveScene("start", ids), 0);
  assert.equal(P.resolveScene("waited", ids), 2);
});

test("resolveScene returns -1 for a terminal/ending or unknown choice", () => {
  const ids = ["a", "b"];
  assert.equal(P.resolveScene("", ids), -1);           // no target -> ending choice
  assert.equal(P.resolveScene(null, ids), -1);
  assert.equal(P.resolveScene("nowhere", ids), -1);    // dangling target -> ending
  assert.equal(P.resolveScene("a", []), -1);           // no scenes at all
});

// --------------------------------------------------------------- aggregate score + subscores (M13)

test("aggregateScore with NO objectives counts every KC (pre-M13 graded course unchanged)", () => {
  const items = [{obj: null, ok: true}, {obj: null, ok: true}, {obj: null, ok: false}, {obj: null, ok: false}];
  const s = P.aggregateScore(items, 80, []);
  assert.equal(s.raw, 50);              // 2 of 4
  assert.equal(s.passed, false);        // 50 < 80
  assert.deepEqual(s.objectives, []);
  assert.equal(s.scaled, "0.50");
});

test("aggregateScore counts only summative (tagged) KCs; inline KCs are formative", () => {
  // two Safety KCs (both right) + one inline KC (wrong). With objectives present the
  // inline KC does not drag the overall down.
  const items = [{obj: "safety", ok: true}, {obj: "safety", ok: true}, {obj: null, ok: false}];
  const s = P.aggregateScore(items, 80, [{id: "safety", name: "Safety", pass: 70}]);
  assert.equal(s.raw, 100);             // 2 of 2 summative
  assert.equal(s.passed, true);
});

test("aggregateScore reports per-objective subscores and thresholds", () => {
  const items = [
    {obj: "safety", ok: true}, {obj: "safety", ok: true},   // safety 100
    {obj: "billing", ok: true}, {obj: "billing", ok: false} // billing 50
  ];
  const objs = [{id: "safety", name: "Safety", pass: 70}, {id: "billing", name: "Billing", pass: 60}];
  const s = P.aggregateScore(items, 50, objs);
  assert.equal(s.raw, 75);              // 3 of 4 overall
  const byId = Object.fromEntries(s.objectives.map(o => [o.id, o]));
  assert.equal(byId.safety.raw, 100);
  assert.equal(byId.safety.passed, true);
  assert.equal(byId.billing.raw, 50);
  assert.equal(byId.billing.passed, false);   // 50 < 60
});

test("aggregateScore fails overall when a SECTION threshold fails even if raw >= passMark", () => {
  // overall 75 >= passMark 50, but billing 50 < its 60 threshold → course fails.
  const items = [
    {obj: "safety", ok: true}, {obj: "safety", ok: true},
    {obj: "billing", ok: true}, {obj: "billing", ok: false}
  ];
  const objs = [{id: "safety", name: "Safety", pass: 70}, {id: "billing", name: "Billing", pass: 60}];
  const s = P.aggregateScore(items, 50, objs);
  assert.equal(s.raw, 75);
  assert.equal(s.passed, false);       // a failed section gates the overall
});

test("aggregateScore: a null-threshold objective reports a subscore but never blocks", () => {
  const items = [{obj: "intro", ok: false}, {obj: "intro", ok: false}];
  const s = P.aggregateScore(items, 0, [{id: "intro", name: "Intro", pass: null}]);
  assert.equal(s.objectives[0].raw, 0);
  assert.equal(s.objectives[0].passed, true);   // no threshold → always "passed"
  assert.equal(s.passed, true);                 // raw 0 >= passMark 0, no section gate
});

test("aggregateScore is safe with empty input", () => {
  const s = P.aggregateScore([], 80, []);
  assert.equal(s.raw, 0);
  assert.equal(s.passed, false);       // 0 < 80
});

// --------------------------------- M12→M13: fractional partial credit in the aggregate

test("aggregateScore takes FRACTIONAL {got,max} credit from M12 blocks", () => {
  // one KC (right = 1/1) + one 3-pair matching block scored 2/3 (partial credit).
  const items = [{obj: "terms", ok: true}, {obj: "terms", got: 2, max: 3, ok: false}];
  const s = P.aggregateScore(items, 70, [{id: "terms", name: "Terms", pass: 70}]);
  assert.equal(s.raw, 75);             // (1+2) of (1+3) points
  assert.equal(s.objectives[0].raw, 75);
  assert.equal(s.objectives[0].passed, true);   // 75 >= 70
  assert.equal(s.passed, true);
});

test("aggregateScore weights per-sub-item: a 3-item block outweighs one KC", () => {
  // KC wrong (0/1) + matching all-right (3/3). Per-sub-item → 3/4 = 75 (NOT 50, which is
  // what per-block-normalized weighting would give). Pins the locked weighting choice.
  const items = [{obj: "o", ok: false}, {obj: "o", got: 3, max: 3, ok: true}];
  const s = P.aggregateScore(items, 70, [{id: "o", name: "O", pass: null}]);
  assert.equal(s.raw, 75);
  assert.equal(s.passed, true);        // 75 >= 70, null threshold never blocks
});

test("aggregateScore treats a boolean item as got/max = ok/1 (backward compatible)", () => {
  // a plain KC {ok} must behave identically to {got:ok?1:0, max:1} — mixed with a 1/3 block.
  const items = [{obj: null, ok: true}, {obj: null, got: 1, max: 3, ok: false}];
  const s = P.aggregateScore(items, 80, []);
  assert.equal(s.raw, 50);             // (1+1) of (1+3)
});

test("real tallyExact / fillScore output plugs into aggregateScore as fractional items", () => {
  const t = P.tallyExact(["b", "b", "c"], ["a", "b", "c"]);   // 2 of 3
  const f = P.fillScore(["blue"], [["blue", "azure"]]);        // 1 of 1
  const items = [
    {obj: "o", ok: t.ok, got: t.got, max: t.max},
    {obj: "o", ok: f.ok, got: f.got, max: f.max},
  ];
  const s = P.aggregateScore(items, 60, [{id: "o", name: "O", pass: 60}]);
  assert.equal(s.raw, 75);             // (2+1) of (3+1)
  assert.equal(s.objectives[0].raw, 75);
  assert.equal(s.objectives[0].passed, true);
});

// --------------------------------- C5: question-bank draw + option shuffle (pure)

test("drawPool is deterministic per seed and returns sorted indices", () => {
  assert.deepEqual(P.drawPool(4, 2, P.makeRng(42)), [0, 3]);
  assert.deepEqual(P.drawPool(4, 2, P.makeRng(42)), [0, 3]);   // same seed -> same draw (resume-stable)
  // sorted so the drawn subset keeps authored order
  const d = P.drawPool(6, 3, P.makeRng(99));
  assert.deepEqual(d.slice().sort((a, b) => a - b), d);
});

test("drawPool with a different seed draws a different subset (proves retry re-draw would differ)", () => {
  assert.deepEqual(P.drawPool(4, 2, P.makeRng(7)), [1, 2]);
  assert.notDeepEqual(P.drawPool(4, 2, P.makeRng(7)), P.drawPool(4, 2, P.makeRng(42)));
});

test("drawPool draws ALL when n >= pool size (no randomization)", () => {
  assert.deepEqual(P.drawPool(3, 5, P.makeRng(1)), [0, 1, 2]);
  assert.deepEqual(P.drawPool(3, 3, P.makeRng(123)), [0, 1, 2]);
});

test("seededShuffle is a valid, deterministic permutation", () => {
  assert.deepEqual(P.seededShuffle(4, P.makeRng(7)), [2, 1, 3, 0]);
  const s = P.seededShuffle(5, P.makeRng(9));
  assert.deepEqual(s.slice().sort((a, b) => a - b), [0, 1, 2, 3, 4]);   // every index exactly once
});

test("packBank keeps the drawn pick and drops the cosmetic option order", () => {
  assert.deepEqual(P.packBank({0: {pick: [0, 2], opt: {0: [1, 0]}}}), {0: {pick: [0, 2]}});
  assert.equal(P.packBank(undefined), undefined);   // non-bank course: no-op
});

test("fitSuspend threads bank state and never drops `pick`, even at the tightest rung", () => {
  // a pathological state that blows the 1.2 budget forces the smallest rung; `pick` must survive.
  const big = {};
  for (let i = 0; i < 400; i++) big["kc" + i] = {opt: "0,1,2", ok: 1, multi: 1};
  const state = {g: [], k: big, m: [], o: [], s: {}, mt: {}, sq: {}, fl: {},
    b: {0: {pick: [1, 4], opt: {0: [2, 0, 1]}}}, loc: {t: "kc", i: 3}};
  const packed = JSON.parse(P.fitSuspend(state));
  assert.deepEqual(packed.b[0].pick, [1, 4]);        // draw preserved -> resume shows same questions
  assert.equal(packed.b[0].opt, undefined);          // option order dropped under pressure (cosmetic)
});

// --------------------------------------------------------------- matching scorer (M12)

test("tallyExact gives full credit when every pick matches", () => {
  const r = P.tallyExact(["p1", "p2", "p3"], ["p1", "p2", "p3"]);
  assert.deepEqual(r, { got: 3, max: 3, ok: true });
});

test("tallyExact gives PARTIAL credit and is not ok when some are wrong", () => {
  const r = P.tallyExact(["p1", "pX", "p3"], ["p1", "p2", "p3"]);
  assert.equal(r.got, 2);
  assert.equal(r.max, 3);
  assert.equal(r.ok, false);
});

test("tallyExact counts a blank/missing pick as wrong (never auto-passes)", () => {
  assert.deepEqual(P.tallyExact(["", "p2"], ["p1", "p2"]), { got: 1, max: 2, ok: false });
  assert.deepEqual(P.tallyExact([null, "p2"], ["p1", "p2"]), { got: 1, max: 2, ok: false });
  assert.deepEqual(P.tallyExact([], ["p1", "p2"]), { got: 0, max: 2, ok: false });
});

test("packSeen drops picks but keeps ok + got/max", () => {
  assert.deepEqual(P.packSeen({ mt0: { ok: false, got: 2, max: 3, picks: ["p1", "pX", "p3"] } }),
    { mt0: { ok: 0, got: 2, max: 3 } });
});

// --------------------------------------------------------------- sequencing scorer (M12)

test("tallyExact scores sequencing positions with partial credit", () => {
  // answers are the correct positions per rendered (reversed) row; picks are the learner's.
  assert.deepEqual(P.tallyExact(["4", "3", "2", "1"], ["4", "3", "2", "1"]),
    { got: 4, max: 4, ok: true });                       // perfect order
  const r = P.tallyExact(["4", "1", "2", "3"], ["4", "3", "2", "1"]);
  assert.equal(r.got, 2);                                // only #4 and #2 landed right
  assert.equal(r.ok, false);
});

// --------------------------------------------------------------- fill-in-the-blank scorer (M12)

test("normFill trims, collapses whitespace, and lowercases", () => {
  assert.equal(P.normFill("  Paris  "), "paris");
  assert.equal(P.normFill("New   York"), "new york");
  assert.equal(P.normFill(null), "");
});

test("fillScore matches leniently against the accept-list with partial credit", () => {
  const answerSets = [["Paris", "paris"], ["0", "zero"]];
  assert.deepEqual(P.fillScore([" PARIS ", "zero"], answerSets), { got: 2, max: 2, ok: true });
  const r = P.fillScore(["Paris", "5"], answerSets);
  assert.equal(r.got, 1);                                // second blank wrong
  assert.equal(r.ok, false);
});

test("fillScore counts a blank input as wrong (never auto-passes)", () => {
  assert.deepEqual(P.fillScore(["", "zero"], [["paris"], ["zero"]]), { got: 1, max: 2, ok: false });
});

// --------------------------------------------------------------- points/XP overlay (gamification #3)

test("xpCat maps each block kind to its weight category", () => {
  assert.equal(P.xpCat("kc"), "check");
  assert.equal(P.xpCat("sort"), "check");
  assert.equal(P.xpCat("mt"), "question");
  assert.equal(P.xpCat("sq"), "question");
  assert.equal(P.xpCat("fl"), "question");
  assert.equal(P.xpCat("dd"), "question");
  assert.equal(P.xpCat("ws"), "game");
  assert.equal(P.xpCat("cw"), "game");
});

test("xpWeight falls back to the default weights when none supplied", () => {
  assert.equal(P.xpWeight("kc"), 10);        // default check
  assert.equal(P.xpWeight("mt"), 15);        // default question
  assert.equal(P.xpWeight("ws"), 20);        // default game
  assert.equal(P.xpWeight("ws", { check: 10, question: 15, game: 25 }), 25);   // override
});

test("xpForResult: boolean blocks are all-or-nothing, partial blocks pro-rata", () => {
  // a KC has no got/max → all-or-nothing on ok
  assert.equal(P.xpForResult("kc", { ok: true }), 10);
  assert.equal(P.xpForResult("kc", { ok: false }), 0);
  // a partial-credit block awards weight * got/max, rounded
  assert.equal(P.xpForResult("mt", { ok: false, got: 2, max: 4 }), 8);   // 15 * 2/4 = 7.5 → 8
  assert.equal(P.xpForResult("cw", { ok: true, got: 3, max: 3 }), 20);   // full game
  assert.equal(P.xpForResult("ws", { got: 1, max: 4 }, { check: 10, question: 15, game: 40 }), 10); // 40*1/4
  assert.equal(P.xpForResult("mt", null), 0);                            // unresolved earns nothing
  assert.equal(P.xpForResult("mt", { got: 1, max: 0 }), 0);              // max 0 → no divide-by-zero
});

test("xpTotals sums earned + earnable across kinds", () => {
  const specs = [
    { kind: "kc", seen: { 0: { ok: true }, 1: { ok: false } }, count: 3 },   // 1 of 3 checks right
    { kind: "cw", seen: { cw0: { got: 2, max: 4 } }, count: 1 }              // half a game
  ];
  const t = P.xpTotals(specs);
  // earnable = 3*10 (checks) + 1*20 (game) = 50; earned = 10 (one kc) + 10 (20*2/4) = 20
  assert.equal(t.possible, 50);
  assert.equal(t.earned, 20);
});

test("tierFor returns the highest tier the fraction has reached", () => {
  const tiers = [["Novice", 0.0], ["Proficient", 0.5], ["Skilled", 0.8], ["Expert", 1.0]];
  assert.equal(P.tierFor(0.0, tiers).name, "Novice");
  assert.equal(P.tierFor(0.49, tiers).name, "Novice");
  assert.equal(P.tierFor(0.5, tiers).name, "Proficient");
  assert.equal(P.tierFor(0.85, tiers).name, "Skilled");
  assert.equal(P.tierFor(1.0, tiers).name, "Expert");
  assert.equal(P.tierFor(1.0, tiers).index, 3);
  assert.equal(P.tierFor(0.3).name, "Novice");    // defaults when tiers omitted
});
