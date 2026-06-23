"""Brand profile loader — makes "brand" a swappable drop-in layer.

A brand profile is a directory under `brands/` (or an absolute path) containing:
    brand.json                      the manifest (values below)
    tokens.css                      CSS custom properties (the --brand-* vars)
    <logo>  <favicon>  fonts/       brand assets
    transitions/<color>-<band>.png  optional ribbon art (absent => CSS band fallback)
    backgrounds/  icons/            optional art for the cover compositor

`load_brand()` resolves a profile by name (default "_default"), overlaying its
brand.json on the neutral fallback so any missing key degrades gracefully. The
engine ships brands/_default (neutral, no client data); each client is its own
profile (e.g. brands/acme). The system is brand-agnostic — nothing
client-specific is hardcoded; it all lives in a profile.
"""
import os, json

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BRANDS_DIR = os.path.join(ROOT, "brands")
DEFAULT = "_default"

# Neutral fallback for any key a profile's brand.json omits (and the floor when no
# profile resolves at all). Deliberately generic — zero client identity.
FALLBACK = {
    "name": "Course",
    "defaultAccent": "#3B82F6",
    "palette": {},                 # {name: hex} — informational / for prompts
    "accentSnap": [],              # accent-eligible hexes; [] => Rise-import accent passes through
    "sectionColors": [],           # names with transitions/<name>-<band>.png; [] => CSS band
    "logo": "logo.svg",
    "favicon": "favicon.png",
    "logoAlt": "",
    "fonts": {
        "body": "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
        "head": "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
    },
    "cmi5IdBase": "https://example.org/cmi5",
    "promptStyle": ("Clean, calm, professional vector illustration: soft shapes, rounded edges, "
                    "generous whitespace, small accent use, one clear idea per image. Avoid readable "
                    "text, photorealism, anime, glossy 3D, and mascots."),
    "promptHierarchy": "Use the brand accent as the dominant color with one or two neutral supporting tones.",
    "renderingName": "calm-vector",
}


class Brand:
    def __init__(self, name, path, default_path, data):
        self.name = data.get("name", name)
        self.path = path                  # resolved profile dir (assets) or None
        self._default_path = default_path  # brands/_default (asset fallback)
        self.data = data

    def get(self, key, fallback=None):
        return self.data.get(key, fallback)

    @property
    def accent(self):
        return self.data.get("defaultAccent", FALLBACK["defaultAccent"])

    def asset(self, rel):
        """Absolute path to a profile asset, falling back to brands/_default, else None."""
        for base in (self.path, self._default_path):
            if base:
                p = os.path.join(base, rel)
                if os.path.exists(p):
                    return p
        return None

    def has_transitions(self):
        d = self.asset("transitions")
        return bool(d) and os.path.isdir(d)


def _resolve_dir(name_or_dir, root):
    if name_or_dir and os.path.isdir(name_or_dir):
        return os.path.abspath(name_or_dir)
    cand = os.path.join(root, "brands", name_or_dir or DEFAULT)
    return cand if os.path.isdir(cand) else None


def _read_manifest(d):
    if d:
        mf = os.path.join(d, "brand.json")
        if os.path.isfile(mf):
            try:
                return json.load(open(mf, encoding="utf-8"))
            except (ValueError, OSError):
                pass
    return {}


def load_brand(name_or_dir=DEFAULT, root=ROOT):
    """Resolve a brand profile. data = FALLBACK <- _default/brand.json <- <profile>/brand.json."""
    default_dir = os.path.join(root, "brands", DEFAULT)
    profile_dir = _resolve_dir(name_or_dir, root)
    data = dict(FALLBACK)
    data.update(_read_manifest(default_dir))
    if profile_dir and profile_dir != default_dir:
        data.update(_read_manifest(profile_dir))
    return Brand(name_or_dir, profile_dir or default_dir, default_dir if os.path.isdir(default_dir) else None, data)
