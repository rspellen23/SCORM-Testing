"""Course Builder — structured build report.

The engine never crashes on malformed input: it drops to empty and keeps going.
For a hands-on author that's a feature; for an *operator* running real workloads
it's the central liability — a dropped block or a mis-scored quiz ships unnoticed.

This module turns the build's scattered, stderr-only signals (IR import warnings,
the §8 lint pass, the PowerPoint flatten's dropped-block set, SCORM conformance
lint) into ONE structured report that travels with the build:

    report = assemble(ir, lint_errors=…, dropped=…, conformance_errors=…, conformance_warnings=…)
    write(report, out_path)          # -> <stem>.report.json next to the artifact

The dashboard reads that JSON back (the build runs in a subprocess, so the report
must cross the process boundary on disk) and shows the operator, in the UI, when
a build degraded — not just in stderr. The on-disk JSON is also the persistence:
every build leaves its report beside the artifact.

`assemble` is pure (dict in, dict out) so it can be unit-tested without a build.
"""
import json
import os

REPORT_SUFFIX = ".report.json"


def report_path(out_path):
    """The report path for a build artifact: `<stem>.report.json` beside it.

    Shared by the writer (CLI) and the reader (dashboard) so both derive the
    same location from the artifact path alone — no out-of-band handshake.
    """
    return os.path.splitext(out_path)[0] + REPORT_SUFFIX


def assemble(ir, *, lint_errors=None, dropped=None,
             conformance_errors=None, conformance_warnings=None):
    """Build the structured report from a build's signals. Pure.

    - `ir`                  the Course IR (its `_stats` carries blocks/assets and
                            any import-time drop WARNINGS recorded by md_import).
    - `lint_errors`         the §8 `authoring.lint` errors (KC mis-scoring, missing
                            chart source, …) — correctness problems, surfaced as ERRORS
                            even though a package was still produced.
    - `dropped`             {block_type: count} the PowerPoint flatten couldn't render
                            statically (only meaningful for a .pptx build).
    - `conformance_*`       SCORM conformance lint results (when `--validate`).

    Returns: {title, blocks, assets, warnings[str], errors[str], dropped{}, ok}.
    `ok` is False when anything correctness-level (lint or conformance ERROR) is
    present, so the dashboard can flag an otherwise-"successful" build as suspect.
    """
    st = (ir.get("_stats") or {}) if isinstance(ir, dict) else {}
    warnings = list(st.get("warnings") or [])           # import-time drops (e.g. missing assets)
    errors = []

    # rise_import records unsupported block variants it couldn't map as `skipped`
    # ({"fam/var": count}) — the same silent-drop disease; surface them too.
    for variant, c in (st.get("skipped") or {}).items():
        if c:
            warnings.append(f"{c} “{variant}” source block(s) had no equivalent and were skipped on import")

    dropped = {k: v for k, v in (dropped or {}).items() if v}
    for t, c in dropped.items():
        warnings.append(
            f"{c} “{t}” block(s) had no static equivalent and were dropped "
            f"from the PowerPoint")

    for w in (conformance_warnings or []):
        warnings.append(f"SCORM conformance: {w}")

    for e in (lint_errors or []):
        errors.append(e)
    for e in (conformance_errors or []):
        errors.append(f"SCORM conformance: {e}")

    return {
        "title": ir.get("title") if isinstance(ir, dict) else None,
        "blocks": st.get("blocks"),
        "assets": st.get("assets"),
        "warnings": warnings,
        "errors": errors,
        "dropped": dropped,
        "ok": not errors,
    }


def write(report, out_path):
    """Persist `report` to `<stem>.report.json` beside the artifact. Returns the path.

    Best-effort: a write failure must never fail an otherwise-good build, so it is
    swallowed (the build report is observability, not the deliverable).
    """
    p = report_path(out_path)
    try:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
    except OSError:
        return None
    return p


def read(out_path):
    """Read the report beside an artifact, or None if absent/unreadable."""
    p = report_path(out_path)
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None
