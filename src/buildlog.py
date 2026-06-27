"""Course Builder — central logging setup.

The engine historically never used `logging`: malformed input silently dropped
to `""`/empty and the only signal was a one-shot `print` (or nothing). For an
*operator* running batches that is the central liability — a dropped block or a
mis-scored quiz ships unnoticed. This module gives the engine one real logging
channel so degradation is recorded the moment it happens, at the site where it
happens, instead of being swallowed.

Usage at a drop site:

    from buildlog import get_logger
    log = get_logger(__name__)
    log.warning("visual slot %r had no matching file in %s — image dropped", slot, image_dir)

The structured *build report* (`build_report.py`) is the operator-facing surface;
this is the plumbing underneath it. Logs go to stderr (captured by the dashboard
subprocess and shown in the per-job log), at INFO and above.
"""
import logging
import sys

_ROOT = "coursebuilder"
_configured = False


def _configure():
    """Attach a single stderr handler to the `coursebuilder` logger, once.

    Idempotent and library-safe: we configure only OUR namespace (never the root
    logger), so importing the engine never hijacks a host application's logging.
    """
    global _configured
    if _configured:
        return
    logger = logging.getLogger(_ROOT)
    if not logger.handlers:
        h = logging.StreamHandler(sys.stderr)
        h.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        logger.addHandler(h)
    logger.setLevel(logging.INFO)
    logger.propagate = False           # don't double-log through the root logger
    _configured = True


def get_logger(name=None):
    """Return a logger under the `coursebuilder` namespace (configured on first use).

    Pass `__name__` from the calling module; a bare-script `__main__`/top-level
    name is normalised under the engine namespace so every engine log shares the
    one handler and level.
    """
    _configure()
    if not name or name in ("__main__", _ROOT):
        return logging.getLogger(_ROOT)
    # bare-script imports use the module's own short name (e.g. "md_import"),
    # which isn't dotted under our root — nest it so the handler/level apply.
    if not name.startswith(_ROOT + "."):
        name = f"{_ROOT}.{name}"
    return logging.getLogger(name)
