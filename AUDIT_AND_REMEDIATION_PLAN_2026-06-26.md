# Course Builder — Operator-Readiness Remediation Plan (2026-06-26)

Follow-on to `AUDIT_AND_REMEDIATION_PLAN_2026-06-23.md` (5-pass engineering audit — fully
executed, fixes re-verified to still hold; baseline **137/137 tests green**, HEAD `8509060`).

## Target (scoped with James, 2026-06-26)
**Operator-grade internal tool.** Run by James — or one operator James sets up — to produce
real TeleTracking course/deck workloads at production quality. NOT a multi-tenant SaaS product.
Confirmed operating model:
- **Single operator** ("just me, for now"). → No auth, no multi-tenancy, no concurrent-write
  locking. Design for one; revisit only if people are added.
- **Windows AND Mac.** The operator may run on a PC. → Cross-platform operability is a
  **first-class requirement**, not optional.
- **Mixed / moderate volume** (a handful to a few dozen courses at a time). → **Reliability >
  batch throughput.** A bulk AI-generation pipeline is NOT needed; not silently shipping wrong
  content IS.
- **Two sanctioned subscription providers: Claude CLI AND ChatGPT/Codex CLI** (James, 2026-06-26).
  Both authenticate via a *subscription* login and both scrub any metered API key from the
  environment. The metered-API question is **moot** for this target — no tension with the standing
  rule. (Provider parity work → Phase P.)

## Verdict
**Weeks of hardening, not months.** The distance to "enterprise-workload-ready for one operator"
is: (1) a cluster of silent-correctness bugs the feature sprint introduced, (2) no signal when a
build degrades, (3) the Windows launcher/runbook gap, (4) zero tests on the two product surfaces
(server, player). All tractable. The architecture is sound for a single operator.

## Root cause (unchanged, re-confirmed)
The new bugs are the **same disease** the 06-23 audit named: the engine **never crashes →
malformed input drops to `""`/empty, not flagged.** For a hands-on author that's a feature; for an
**operator running batches it's the central liability** — a dropped block or mis-scored quiz ships
unnoticed. The fix posture for this target is therefore: **fix the bugs AND make degradation
visible** (a build report), not just patch each parser.

## Explicitly OUT of scope for this target (do NOT build)
- Customer-facing API / billing / metering (D.0) — the CLI subscription is the path.
- Authentication, multi-tenancy, per-user isolation, concurrent-write locking (D.1) — single operator.
- Packaging-for-sale / installers-for-strangers / Docker-as-product (D.2) — only "runs on the
  operator's machine" matters (covered by Phase W).
- LICENSE-for-redistribution / stock-image redistribution rights (D.3) — internal use; the only
  live item is scrubbing the engine-source placeholder (A4).

---

## PHASE A — Silent correctness bugs (ships wrong content, no signal) — VERIFIED on disk

- [x] **A1 Multi-select tokenizer leaks bare letters from prose (HIGH).** `md_import.py:957`
  (`_kc_answer_letters`). `re.split(r'[,\s/&]+|\band\b', …)` keeps any single in-range letter, so
  `*Correct Answer:* A, C and also note B` → marks **A, C, B** correct (three; author meant two).
  Docstring claims prose "can't leak in" — false. Silently mis-scores graded quizzes; lint misses it.
  **Fix:** require the RHS to be only label tokens + separators; on any prose word, restrict to the
  pre-prose substring **and** raise it in `lint()`. **DoD:** adversarial input → `[A, C]` or a lint
  failure; regression test in `tests/test_multiselect_kc.py`.

- [x] **A2 Duplicate option labels mis-map the correct answer (HIGH).** `md_import.py:968`
  `{letters.index(a) …}` returns the **first** match only — duplicate-labeled options land the
  correct answer on the wrong one. No crash, no lint error.
  **Fix:** detect duplicate labels in `letters`, flag in `lint()`. **DoD:** duplicate-label KC fails
  lint with a clear message; regression test.

- [x] **A3 Scenario response feedback truncated at `·`/`|` (MED).** `md_import.py:549,551` —
  `_segs` splits on `·`/`|` before `feedback:` is parsed, so those chars inside feedback prose
  silently drop the remediation payload (and `·` is the separator the grammar teaches).
  **Fix:** parse `feedback:` greedily as everything after the last `· feedback:`. **DoD:** feedback
  with `·`/`|` round-trips intact; regression test in `tests/test_branching_blocks.py`.
  **DONE:** `feedback:` is now TERMINAL — `re.search(r'[·|]\s*feedback\s*:\s*(.+)$', raw)` captures
  everything after the first `· feedback:` verbatim; only the head (response text + `preferred`) is
  `_segs`'d. `·`/`|` inside remediation prose round-trip intact. Test
  `test_scenario_feedback_with_separators_survives`.

- [x] **A4 Scrub the brand placeholder in engine source (LOW).** `slide_layouts.py:1763`
  `"name@teletracking.com", "teletracking.com"` — breaks the brand-agnostic claim + neutral-naming
  rule. **Fix:** neutral placeholder (`name@example.com`). **DoD:** `grep -ri teletracking src/` empty.

## PHASE B — New-feature holes & generation robustness (stalls throughput / bad approvals)

- [x] **B1 Lint: multi-scene scenario passes if only ONE scene has choices (MED).** `authoring.py:908`.
  **Fix:** per-scene — every scene with content needs ≥1 response. **DoD:** response-less scene fails lint.
  **DONE:** replaced the global `any(responses)` check with a per-scene one — a scene with narrative
  (`title`/`html`) but no `responses` now fails lint as a dead-end; preferred-choice check retained.
  Tests in `test_lint_validation.py` (dead-end fails, all-with-choices passes).
- [x] **B2 Lint: empty `objectives` block passes (MED).** `md_import.py:578` + no lint rule. With
  auto-objectives effectively requiring it, an empty block ships a lead-in with no outcomes.
  **Fix:** lint error on `objectives` with no `items`. **DoD:** empty objectives fails lint.
  **DONE:** lint now errors on an `objectives` block with no `items` (`authoring.lint`); tests added.
- [x] **B3 Chart render crashes on non-numeric data (HIGH).** `chart_svg.py:273` — the SR data table
  `int(v)` throws on `"N/A"`/`null` (which LLMs emit), killing the whole chart. **Fix:** guard
  `_fmt(v) if isinstance(v,(int,float)) else ""`. **DoD:** chart with a bad cell renders; regression test.
  **DONE:** hardened the single chokepoint `_fmt` (numbers as before; `None`→`""`; any other value →
  `str(v)`, so `"N/A"` shows verbatim instead of crashing). Tests in `test_chart_guardrail.py`.
- [x] **B4 SVG preview hides full-bleed images (HIGH — breaks preview==pptx).** `slide_svg.py:79` — the
  mock no-ops alpha, so `image mode:"full"` shows a solid slab in preview while the `.pptx` shows the
  photo. Operator approves the wrong thing. **Fix:** mock `_Shape` settable alpha → `fill-opacity`.
  **DoD:** full-bleed preview shows the image; `test_slide_svg.py` asserts the opacity attr.
  **DONE:** mock `_Shape` gained `set_alpha()`→`fill-opacity` (and, while there, real outline rendering:
  `_Line.width`→`stroke`), and `_fill_alpha` duck-types the mock. Full-bleed preview now shows the photo
  under a translucent scrim. Tests assert the opacity attr.
- [x] **B5 `cycles` hub invisible in light theme + uncapped steps + lying docstring (HIGH).**
  `slide_layouts.py:1894,1862`. **Fix:** outline the hub; cap steps to 6; correct the docstring.
  **DoD:** light-theme hub visible; >6-step cycles caps; raster-verify both themes.
  **DONE:** hub now carries a `hubOutlineColor`/`hubOutlinePt` stroke (rule_color/1.25pt) so it's visible
  on a same-tone bg; steps capped `[:6]`; docstring corrected (no pagination — a cycle stays whole).
  Raster-verified BOTH themes (teletracking light+dark): light-theme PDCA hub is a clearly-outlined disc.
- [x] **B6 `_fit_pt` floor overflows silently (MED).** `slide_layouts.py:511` — returns `min_pt` even
  when text still overflows; bleeds past bounds. **Fix:** hard-truncate with ellipsis at the floor.
  **DONE:** new `_box_capacity_chars()` (same 0.50*pt-width / 1.2-line metric as `_fit_pt`) + `_fit_body()`
  returning `(pt, text)` — runs `_fit_pt`, and if the text STILL exceeds the box's char capacity at the
  floor, hard-truncates with an ellipsis so it can't bleed past bounds; fitting text returns unchanged. The
  three body call sites (timeline / cards / cycles) switched `bpt = _fit_pt(...)` → `bpt, body = _fit_body(...)`.
  Tests in `test_robustness_polish.py` (fits-unchanged, overflow→ellipsis≤capacity, empty-safe).
- [x] **B7 Multi-select PPTX flatten lacks a "select all" cue (MED).** `pptx_export.py:292` — multiple
  `✓`, no "choose all that apply." **Fix:** prepend the cue when `b.get("multi")`. **DoD:** cue present.
  **DONE:** `_render_kc` adds an italic "Select all that apply." paragraph after the prompt when
  `b.get("multi")`; single-select KCs are unchanged. Tests assert the cue is present for a multi KC and
  absent for a single.
- [x] **B8 Player a11y: correct-answer reveal is color-only (MED).** `player.js:336,343` — no per-option
  sr-only marker; locked options stay tab-focusable; empty-Submit is a silent no-op. **Fix:** sr-only
  `(correct answer)`/`(incorrect)` per option; `o.disabled=true` on lock; polite prompt on empty Submit.
  **DoD:** SR announces which options were correct; covered by C2's node test.
  **DONE:** new `srMarkOpt(o)` appends an off-screen `(correct answer)`/`(incorrect)` tag (class `nv-kc-mark`,
  idempotent) to each locked option in `lockKc`/`lockKcMulti` and on single-select retry-elimination, so the
  verdict isn't color-only; each locked/eliminated `<button>` now gets `o.disabled=true` (off the tab order,
  not just `pointer-events:none`); the multi empty-Submit no-op now shows a polite "Select at least one option,
  then choose Submit." in the `aria-live` feedback region. The graded-retry reset clears `disabled` + removes
  the `nv-kc-mark` tags so re-locking is clean. `node --check` passes; player node suite (10) still green.
  (DOM markers aren't unit-tested by the pure-helper node harness — verified by inspection + a browser pass is
  the human review item.)

## PHASE W — Windows / cross-platform operability (NEW — the operator may run on a PC)

Recon (2026-06-26) confirms the heavy lifting is already done: `textutil` is `shutil.which`-guarded
with pure-Python fallbacks; the reveal/open path is already branched darwin/linux/win
(`server.py:812`); `/Volumes` is `isdir`-guarded; paths use `expanduser`/`os.path.join`. Gaps are small:

- [x] **W1 Windows launcher (HIGH for this target).** `dashboard/launch.command` (bash) + `build` (sh)
  are Unix-only. **Fix:** add `dashboard/launch.bat` (and/or `launch.ps1`) running
  `python dashboard\server.py`, and a `build.bat` wrapping `python src\cli.py %*`. **DoD:** a PC operator
  double-clicks `launch.bat`, the dashboard opens; `build.bat from-md …` builds a SCORM zip on Windows.
  **DONE:** added `dashboard/launch.bat` + `dashboard/launch.ps1` (both `cd` to repo root, prefer `python`
  then fall back to the `py` launcher, run `dashboard\server.py`, and pause/print a PATH hint on failure)
  and a root `build.bat` mirroring the `./build` sh wrapper (same help text + flow-through `%PY% src\cli.py %*`,
  `py` fallback). README + server.py docstring now name the Windows launchers. Existence/invocation guarded by
  `tests/test_windows_operability.py`. (A real double-click pass is W4, the human-gated oracle.)
- [x] **W2 Tesseract-on-Windows note + graceful skip (MED).** OCR needs the binary. **Fix:** verify the
  `requirements.txt` install note is Windows-accurate (UB-Mannheim build + PATH) and that no-Tesseract
  degrades to a clear "skipped — install Tesseract" note (it already should — confirm on Windows).
  **DoD:** on a Windows box with no Tesseract, image sources skip with an actionable note, no crash.
  **DONE:** found a real gap — the UB-Mannheim installer drops `tesseract.exe` in `C:\Program Files\
  Tesseract-OCR\` and does NOT add it to PATH, so `shutil.which("tesseract")` missed it → a Windows operator
  who *installed* OCR still got "install Tesseract" and silent OCR failure. New `_tesseract_cmd()` probes the
  `ProgramFiles`/`ProgramFiles(x86)` default install path on Windows when `which` misses and points
  `pytesseract.pytesseract.tesseract_cmd` at it; genuine-absence still returns None → the existing skip-with-hint
  path (`_skip_reason`) is unchanged, so no-Tesseract still degrades cleanly (no crash). `requirements.txt` note
  updated (auto-detects the default location; PATH only needed for a non-default install). Tests cover on-PATH,
  off-PATH-but-installed, and absent (Windows + non-Windows) in `tests/test_windows_operability.py`.
- [x] **W3 Windows path roots (LOW).** `_within_roots` (`server.py:50`) has no drive-letter analogue to
  `/Volumes`; a source on `D:\` falls outside the allowlist → navigator clamps to home. **Fix:** on
  Windows, allow the home drive root (or accessible fixed drives) so external-drive sources work.
  **DoD:** a course folder on a second drive is reachable from the navigator on Windows.
  **DONE:** factored the OS-specific extra roots into `_platform_drive_roots()` — macOS `/Volumes` (unchanged),
  Windows = each accessible drive root (`C:\`, `D:\`, … `isdir`-filtered, the direct `/Volumes` analogue),
  Linux = none. `_allow_roots()` folds them in. Existing `_within_roots` symlink-resolution + `commonpath`
  cross-drive guard already handle the rest. Unit tests pin the Windows/macOS/Linux branches + that
  `_allow_roots` includes them. (Reaching a real `D:\` folder end-to-end is part of the W4 Windows smoke.)
- [ ] **W4 End-to-end Windows smoke (HIGH gate).** Once W1–W3 land: on a real Windows machine, run the
  dashboard + a `build.bat from-md` + a `claude`-CLI generation, and a `.docx`/`.html` ingest.
  **DoD:** a documented clean pass on Windows (the only way to truly close Phase W — like PowerPoint
  animation, James/the operator is the oracle here).

## PHASE P — ChatGPT (OpenAI Codex) provider parity — REQUIREMENT (James, 2026-06-26)

Recon (2026-06-26): the `codex` provider **already exists and is wired end-to-end** — engine
(`run_cli` codex branch, `authoring.py:714`: `codex exec --sandbox read-only --output-last-message
<f> -`), a UI provider dropdown in both tabs (`gen_provider`/`sl_provider`, populated from
`provider_status()` via `/api/ai-status`), project-meta persistence, and install/login detection.
Labeled "ChatGPT (OpenAI Codex subscription)"; **scrubs `OPENAI_API_KEY`/`CODEX_API_KEY` so it
authenticates via the ChatGPT subscription, never a metered key** (honors the standing rule). It is
**not installed on this machine and has never been run live.** Remaining work is VERIFY + POLISH:

- [ ] **P1 End-to-end verification with a real ChatGPT login (HIGH — the unproven sliver).** Install
  `@openai/codex`, run `codex` → "Sign in with ChatGPT." Generate a real multi-unit course + a deck
  with provider=codex. Confirm the headless `codex exec` invocation works **without an approval-prompt
  hang** (the codex analogue of the claude cold-subprocess saga) and the output lints clean.
  **DoD:** a documented clean codex generation of a course + deck. *(Needs James: install + login + run.)*
- [x] **P2 Provider-aware model selector (MED).** The model dropdown (Haiku/Sonnet/Opus) is
  claude-specific; `run_cli` ignores `model` for codex, so "ChatGPT + Sonnet" silently no-ops the model.
  **Fix:** when provider=codex, hide/disable the claude model control (codex picks its model via its own
  login) — or offer codex model options and map to codex `-m` if supported. **DoD:** choosing ChatGPT
  never shows a silently-ignored model control.
  **DONE:** new `syncModelCtl()` disables + dims the model row and swaps the hint to "ChatGPT (Codex)
  selects its own model … this control is ignored" for any non-claude provider; restores on claude. Wired
  to both provider selects' `onchange`, into `applyProviders` (initial + re-check), and the project-meta
  restore. Static drift guards in `tests/test_provider_model_ui.py`; node logic check confirms
  claude↔codex↔restore. P1/P3 still need James (install `@openai/codex` + ChatGPT login for a live run).
- [ ] **P3 Prompt parity check (MED).** Prompts were tuned against Claude; GPT may parse the §8 grammar
  + JSON-only instructions differently. **Fix:** compare a codex run's lint-pass rate + format adherence
  to claude; provider-condition the prompt only if needed. **DoD:** codex output meets the same
  lint/format bar, or a documented prompt tweak that gets it there.
- [ ] **P4 Real codex streaming (LOW, enhancement).** `run_cli_stream` falls back to non-streaming for
  codex (`authoring.py:773` — one chunk at the end), so the live view shows nothing until done. `codex
  exec` JSON event output could feed `on_chunk`. **DoD:** live token streaming for codex. Defer unless
  the operator wants the live view.

## PHASE C — Observability + test the product surfaces (so it stays fixed)

- [x] **C1 Structured build-report — make silent drops visible (HIGH for this target).** No `logging`
  anywhere; malformed input drops to empty silently. The 06-23 `stats.dropped` set is the seam.
  **Fix:** a build-report object (warnings + dropped-block list + lint summary) surfaced in the
  dashboard UI and persisted with each build; a real `logging` setup. **DoD:** a build with a
  dropped/malformed block tells the operator, in the UI — not just stderr.
  **DONE (`build_report.py` + `buildlog.py`):** new `src/buildlog.py` = a real `coursebuilder`-namespaced
  `logging` setup (used at the genuine drop site — `md_import` now logs + records each missing-`*Visual:*`
  asset into `_stats["warnings"]`). New `src/build_report.py` = pure `assemble()` folding import warnings +
  the §8 `lint()` pass (run at BUILD time → A1/A2 KC mis-scoring surfaces even for hand-authored md) +
  PowerPoint flatten `dropped` set + rise `skipped` variants + SCORM conformance lint into one report;
  `write()` persists `<stem>.report.json` beside every artifact (the persistence + the subprocess seam).
  `cli._emit`/`cmd_to_pptx`/`cmd_from_md_course` write it; `server.do_build` reads it back per job;
  `index.html` `renderStaged` renders a red(error)/amber(warning) **Build report** panel even on a
  "successful" build. Verified end-to-end (missing image + KC-prose bug → report `ok:false` with both
  surfaced). 13 new tests in `tests/test_build_report.py`; 155/155 green.
- [x] **C2 `dashboard/server.py` has ZERO tests — guard the 06-23 security fixes (HIGH).** A future edit
  silently re-opens the file-read hole. **Fix:** `tests/test_server_endpoints.py` asserting no-token/
  evil-Origin/non-JSON POST → 403, `/etc` readjson blocked, `/preview` traversal 404, bogus brand
  rejected. **DoD:** the guards are regression-tested in CI.
  **DONE (`tests/test_server_endpoints.py`, 13 tests):** a live `ThreadingHTTPServer` fixture (free port,
  daemon thread) hit with `http.client` exercises the POST guard end-to-end — no-token / wrong-token /
  evil-Origin / non-JSON-Content-Type all → 403, a fully-valid request → 404-not-403 (positive control,
  proves the guard isn't blanket-rejecting); GET `/api/readjson?path=/etc/passwd` → `ok:false path not
  allowed`; `/preview/etc/passwd` and a `../` traversal → 404; a `../../etc` brand on `/api/deck-svg` →
  500 `unknown brand`. Plus direct unit tests of the primitives (`_within_roots` rejects /etc//etc/passwd//
  empty, accepts home/repo; `_safe_brand` confines to real brands; `_safe_path_arg` rejects flag-like).
  server.py lives in `dashboard/` (off the `pythonpath=src`), so the test adds it to `sys.path`.
- [x] **C3 `player/player.js` has ZERO committed tests (HIGH).** The 06-23 + multi-select fixes were
  verified only by uncommitted `node` scripts. **Fix:** a committed `node` test — multi-select
  all-correct/none-wrong/partial, graded-retry hold-then-pass with a multi-KC, `fitSuspend`→resume for
  `{opt,multi}` incl. the packed rung — wired into the pre-commit hook + CI. **DoD:** player behavior in CI.
  **DONE (`tests/test_player.js`, 10 tests, `node --test`):** extracted the inline KC decisions into pure
  named functions (`multiAllCorrect`, `kcLocks`, `scorePct`, `parseMultiSel`) that the browser handlers
  AND the test both call (de-dupes the retry gate across single/multi handlers too), plus a node-only
  `module.exports` guarded by a `HAS_DOM`-gated DOM bootstrap so `require()` under node defines+exports
  without a DOM. Tests pin: multi-select all-correct/none-wrong/partial/order-independence; the
  retry→lock gate (one-shot always locks, multi-attempt holds a wrong answer to the last try); a graded
  fail→retry→pass crossing the mastery threshold; the `fitSuspend` byte-budget ladder (full `{opt,multi}`
  rung kept when it fits, degraded to the packed `{ok}` rung when an over-budget course overflows 4096 B,
  always valid JSON); `parseMultiSel` packed/empty-rung resume; `utf8len` real UTF-8 byte counting. Wired
  into `.githooks/pre-commit` (node gate, skips if node absent) and `.github/workflows/ci.yml`
  (setup-node + `node --test 'tests/test_*.js'`).
- [x] **C4 Fix the XSS the redesign introduced (MED).** `index.html:994` — `res.skipped.join(', ')`
  injected unescaped (course path at `:1340` correctly escapes). A file named `<img src=x onerror=…>.doc`
  runs JS in the dashboard origin. **Fix:** `.map(esc)`; wrap the other flagged interpolations for
  defense-in-depth. **DoD:** malicious filename renders inert.
- [x] **C5 Bound the ingestion readers (LOW, defense-in-depth).** `authoring.py:265-314` — zip/`Image.open`
  have no size guard (decompression bomb → OOM); `read_sources` no byte cap. **Fix:** check
  `file_size` pre-read, set `Image.MAX_IMAGE_PIXELS`, cap per-file/total bytes. **DoD:** oversized source
  skipped with a note, not OOM.
  **DONE:** four bounds constants (`_MAX_SOURCE_BYTES` 64 MB / `_MAX_TOTAL_SOURCE_BYTES` 256 MB /
  `_MAX_DECOMPRESSED_BYTES` 64 MB / `_MAX_IMAGE_PIXELS` ~64 MP). `read_sources` now checks `os.path.getsize`
  before reading and skips an over-large file — or stops once the running total would exceed the set cap —
  with an actionable note instead of loading it; `_odt_to_text` refuses a member whose DECLARED uncompressed
  size exceeds the cap (the zip-bomb guard); `_ocr_image` sets `Image.MAX_IMAGE_PIXELS` so a pixel-bomb image
  raises (→ skipped) rather than allocating gigabytes. Tests cover the per-file cap, the total-set cap, and the
  .odt decompression guard (plus a small-.odt control).

## PHASE O — Operator runbook (NEW — a one-operator product needs an operator doc)

- [x] **O1 Operator runbook (MED).** A single `OPERATOR_GUIDE.md`: install on Windows + Mac (Python,
  deps, Tesseract, `claude` CLI login), launch, the generate→review→build→export flow, how to read the
  build report, and recover from a failed/partial build. **DoD:** James (or the operator he sets up) can
  stand the tool up on a fresh machine from this doc alone. Pairs with the strong existing
  `AUTHORING_GUIDE.md` (which covers *authoring*, not *operating*).
  **DONE:** `OPERATOR_GUIDE.md` at the repo root — 7 sections: install (Win+Mac prereq table, deps, provider
  login for Claude AND ChatGPT/Codex, the Windows Tesseract auto-detect note), launch (all three launchers),
  the deterministic build CLI (`build`/`build.bat`, every verified subcommand + `--validate`/`--format`/`--brand`),
  the dashboard flow (the real 8 course steps + 3 slide steps), how to read the build report
  (`<stem>.report.json` + the red/amber dashboard panel + that lint runs at build time), a failure→cause→fix
  recovery table, and a quick-reference card. Cross-links AUTHORING_GUIDE/README/BRAND_GUIDE; flags W4 (the
  real-PC smoke) as the operator's to confirm. All CLI commands/flags verified against `src/cli.py`.

---

## Suggested execution order
Reliability first, then where-it-runs, then keep-it-fixed:
**A1 → A2 → A4 → C4** (scoring + the quick XSS) →
**C1** (build report — the operator's eyes) → **B1 → B2 → B3 → B4 → B5** (lint + generation robustness) →
**P2 → P1 → P3** (ChatGPT/codex parity — P2 is code, P1 needs James to install+login) →
**W1 → W2 → W3 → W4** (Windows) →
**C2 → C3** (lock in with tests) → **B6 → B7 → B8 → C5 → P4 → O1** (polish + runbook).

Land A + C4 + C1 first: that's the difference between "silently ships wrong content" and "tells the
operator when something's off" — the single biggest lever for enterprise-workload trust.

## What's deferred but worth tracking (not blockers for this target)
- **Maintainability (M, opportunistic):** `index.html` (99KB inline JS) and `server.py` (1,186 lines)
  are the scariest objects for future work; extract/split when touching them, not as a dedicated effort.
- **Batch AI-generation CLI:** generation is dashboard-only today (the `build` CLI covers the
  deterministic path). NOT needed at mixed/moderate volume; revisit only if volume scales up.
