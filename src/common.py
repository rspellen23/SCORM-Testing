"""Shared helpers: HTML sanitation + slug + asset-name normalisation."""
import re, unicodedata
from html.parser import HTMLParser

# Tags we keep verbatim (no attributes unless whitelisted below).
_KEEP = {"p","br","strong","b","em","i","u","s","sub","sup",
         "ul","ol","li","h1","h2","h3","h4",
         "table","thead","tbody","tfoot","tr","th","td","caption","a"}
# Tags whose wrapper we drop but whose children we keep (Rise's editor cages).
_UNWRAP = {"div","span","font","section","article"}
_ATTR_OK = {"a": {"href"}, "th": {"colspan","rowspan"}, "td": {"colspan","rowspan"}}
_VOID = {"br"}


class _Clean(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []
    def handle_starttag(self, tag, attrs):
        if tag in _UNWRAP:
            return
        if tag in _KEEP:
            ok = _ATTR_OK.get(tag, set())
            kept = "".join(
                ' %s="%s"' % (k, _esc(v)) for k, v in attrs
                if k in ok and v is not None
            )
            self.out.append("<%s%s>" % (tag, kept))
    def handle_endtag(self, tag):
        if tag in _KEEP and tag not in _VOID:
            self.out.append("</%s>" % tag)
    def handle_startendtag(self, tag, attrs):
        if tag in _KEEP:
            self.out.append("<%s>" % tag)
    def handle_data(self, data):
        self.out.append(_esc(data, text=True))


def _esc(s, text=False):
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    if not text:
        s = s.replace('"', "&quot;")
    return s


def clean_html(fragment):
    """Strip Rise editor cages + theme-coupled inline styling; keep semantic HTML."""
    if not fragment:
        return ""
    p = _Clean()
    p.feed(fragment)
    p.close()
    html = "".join(p.out)
    # collapse empty paragraphs / whitespace runs
    html = re.sub(r"<p>\s*</p>", "", html)
    html = re.sub(r"[ \t]+\n", "\n", html).strip()
    return html


def plain_text(fragment):
    """Readable text only — for titles, alt text, slugs."""
    txt = re.sub(r"<[^>]+>", " ", fragment or "")
    txt = re.sub(r"&nbsp;|&#160;", " ", txt)
    txt = re.sub(r"&amp;", "&", txt)
    return re.sub(r"\s+", " ", txt).strip()


def slugify(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s or "course"


def norm_name(s):
    """Normalise an asset filename for fuzzy matching (unicode spaces, case)."""
    s = unicodedata.normalize("NFKC", s or "")
    s = s.replace(" ", " ").replace("\xa0", " ")
    return re.sub(r"\s+", " ", s).strip().lower()
