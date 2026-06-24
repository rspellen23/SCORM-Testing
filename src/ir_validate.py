"""Validate Course IR against schema/ir.schema.json.

`jsonschema` is an OPTIONAL dependency. When it is installed, importer output
is checked against the canonical IR schema and any violation is surfaced; when
it is absent, validation degrades to a no-op so the air-gapped, stdlib-only
SCORM build path keeps working with a bare `python3`.

Two modes:
  - default (lenient): violations are printed to stderr as warnings and the
    build proceeds. This is what the importers/CLI use so a schema gap never
    blocks an author mid-build.
  - strict: a violation raises. Enabled by passing strict=True or by setting
    the env var COURSE_BUILDER_STRICT_SCHEMA=1. The test suite / CI run strict
    so drift between the schema, the importers and the renderer fails the gate.
"""
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PATH = os.path.join(os.path.dirname(_HERE), "schema", "ir.schema.json")

_schema_cache = None

# Current IR shape. Bump when a change to the IR is NOT backward-compatible, and
# register a migration in _MIGRATIONS keyed by the version it upgrades FROM.
CURRENT_IR_VERSION = 1

# version -> function(ir) -> ir, taking an IR at `version` to `version + 1`.
# Empty today: the IR has only ever had one shape, so there is nothing to migrate.
_MIGRATIONS = {}


def migrate(ir, *, label="course"):
    """Upgrade a persisted IR to CURRENT_IR_VERSION before it is built.

    Gives `from-ir` (which round-trips IR JSON edited by hand or saved by an
    older build) a forward-compatibility seam:
      - unversioned/legacy IR is assumed current (the IR has only had one shape);
      - an IR from the FUTURE (newer than this build understands) is refused;
      - older IR is stepped forward through _MIGRATIONS.
    Returns the (possibly migrated) IR; stamps it with the current version.
    """
    if not isinstance(ir, dict):
        return ir
    v = ir.get("irVersion", CURRENT_IR_VERSION)
    if not isinstance(v, int):
        raise ValueError(f"{label}: irVersion must be an integer, got {v!r}")
    if v > CURRENT_IR_VERSION:
        raise ValueError(
            f"{label}: IR is version {v} but this build only understands "
            f"{CURRENT_IR_VERSION}. Upgrade course-builder to load it."
        )
    while v < CURRENT_IR_VERSION:
        step = _MIGRATIONS.get(v)
        if step is None:
            raise ValueError(f"{label}: no migration registered from IR version {v}")
        ir = step(ir)
        v += 1
    ir["irVersion"] = CURRENT_IR_VERSION
    return ir


def load_schema():
    """Load and cache the IR JSON schema."""
    global _schema_cache
    if _schema_cache is None:
        with open(SCHEMA_PATH, encoding="utf-8") as fh:
            _schema_cache = json.load(fh)
    return _schema_cache


def have_jsonschema():
    try:
        import jsonschema  # noqa: F401
        return True
    except ModuleNotFoundError:
        return False


def validate_ir(ir, *, strict=None, label="course"):
    """Validate an IR dict against the canonical schema.

    Returns a list of human-readable error strings (empty when valid, when the
    check is skipped because jsonschema is missing, or when ``ir`` is falsy).

    strict=True raises ValueError listing every violation. When strict is None
    it reads COURSE_BUILDER_STRICT_SCHEMA (== "1" -> strict). In lenient mode
    each violation is echoed to stderr as a "schema warning" and the list is
    still returned so callers can react.
    """
    if strict is None:
        strict = os.environ.get("COURSE_BUILDER_STRICT_SCHEMA") == "1"
    if not ir:
        return []
    try:
        import jsonschema
    except ModuleNotFoundError:
        if strict:
            raise RuntimeError(
                "strict IR validation requested but jsonschema is not installed "
                "(pip install jsonschema, or `pip install -e .[dev]`)"
            )
        return []

    schema = load_schema()
    validator_cls = jsonschema.validators.validator_for(schema)
    validator_cls.check_schema(schema)
    validator = validator_cls(schema)

    errors = []
    for e in sorted(validator.iter_errors(ir), key=lambda x: list(x.path)):
        loc = "/".join(str(p) for p in e.path) or "<root>"
        errors.append(f"{label}: {loc}: {e.message}")

    if errors:
        if strict:
            raise ValueError(
                "IR schema validation failed (%d):\n  %s"
                % (len(errors), "\n  ".join(errors))
            )
        for m in errors:
            print(f"  schema warning: {m}", file=sys.stderr)
    return errors
