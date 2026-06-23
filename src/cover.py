"""Cover / art compositor — composite a background + icon + title into LMS cover art.

Client-agnostic and brand-driven: palette + fonts come from the active brand profile
(src/brand.py). It works with **zero** client art — when no background/icon is supplied
it synthesizes a clean branded gradient + a monogram, so any client can produce covers
with no Figma and no design work. When a brand DOES supply backgrounds/ + icons/ folders
(filled however the client likes — exported from Figma, an icon set, AI, hand-drawn),
those are used instead.

Outputs the three tiles an LMS wants: the square-ish cover (`<name>.png`), a wide hero,
and a tall mobile crop. Pillow only (no SVG rasterizer needed — supply icons as PNG).
"""
import os, glob, textwrap
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# Output dimensions per role (overridable via --size WxH on the CLI).
# Cover is 16:9 to match the topic/path reference templates.
SIZES = {"cover": (1100, 620), "hero": (1920, 480), "mobile": (1080, 1350)}


def _hex(h, default=(59, 130, 246)):
    h = (h or "").lstrip("#")
    if len(h) == 6:
        try:
            return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            pass
    return default


def _mix(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _font(brand, size, bold=True):
    """A TrueType face at `size` — the brand's font if it ships one, else Pillow's bundled DejaVu."""
    fdir = brand.asset("fonts") if brand else None
    if fdir and os.path.isdir(fdir):
        pref = ["ExtraBold", "Bold", "SemiBold", "Condensed-Bold"] if bold else ["Regular", "SemiBold"]
        ttfs = glob.glob(os.path.join(fdir, "*.ttf"))
        for tag in pref:
            for f in ttfs:
                if tag.lower().replace("-", "") in os.path.basename(f).lower().replace("-", ""):
                    try:
                        return ImageFont.truetype(f, size)
                    except OSError:
                        pass
        if ttfs:
            try:
                return ImageFont.truetype(sorted(ttfs)[0], size)
            except OSError:
                pass
    try:
        return ImageFont.load_default(size)        # Pillow >=10 returns a sized DejaVu TrueType
    except TypeError:
        return ImageFont.load_default()


def _cover_fit(img, w, h):
    """Resize+center-crop `img` to exactly w×h (fill, no distortion)."""
    img = img.convert("RGBA")
    s = max(w / img.width, h / img.height)
    img = img.resize((max(1, round(img.width * s)), max(1, round(img.height * s))), Image.LANCZOS)
    x, y = (img.width - w) // 2, (img.height - h) // 2
    return img.crop((x, y, x + w, y + h))


def _gradient(w, h, top, bottom):
    """Vertical two-stop gradient as an RGBA image."""
    base = Image.new("RGB", (1, h))
    px = base.load()
    for y in range(h):
        px[0, y] = _mix(top, bottom, y / max(1, h - 1))
    return base.resize((w, h)).convert("RGBA")


def _background(brand, accent, w, h, path=None):
    if path and os.path.isfile(path):
        return _cover_fit(Image.open(path), w, h)
    # synthesize: a calm diagonal-ish gradient from a darkened accent to near-black ink
    top = _mix(accent, (15, 18, 24), 0.45)
    bot = _mix(accent, (10, 12, 16), 0.82)
    return _gradient(w, h, top, bot)


def _monogram(letter, box, accent, font_face):
    """Synthesize a simple icon: a soft rounded square + the title's initial."""
    img = Image.new("RGBA", (box, box), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = round(box * 0.06)
    d.rounded_rectangle([pad, pad, box - pad, box - pad], radius=round(box * 0.22),
                        fill=(255, 255, 255, 38), outline=(255, 255, 255, 90), width=max(2, box // 90))
    f = font_face(round(box * 0.5))
    t = (letter or "•").upper()[:1]
    l, tp, r, b = d.textbbox((0, 0), t, font=f)
    d.text(((box - (r - l)) / 2 - l, (box - (b - tp)) / 2 - tp), t, font=f, fill=(255, 255, 255, 235))
    return img


def _solid_monogram(letter, box, fill, font_face):
    """A filled rounded-square tile in `fill` with a white initial — a branded icon placeholder
    that reads on a light background (used when no icon asset is supplied)."""
    img = Image.new("RGBA", (box, box), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = round(box * 0.05)
    d.rounded_rectangle([pad, pad, box - pad, box - pad], radius=round(box * 0.20), fill=fill + (255,))
    f = font_face(round(box * 0.52))
    t = (letter or "•").upper()[:1]
    l, tp, r, b = d.textbbox((0, 0), t, font=f)
    d.text(((box - (r - l)) / 2 - l, (box - (b - tp)) / 2 - tp), t, font=f, fill=(255, 255, 255, 255))
    return img


def _tint(icon_rgba, rgb):
    """Recolor a single-color/silhouette icon to `rgb`, preserving its alpha shape."""
    solid = Image.new("RGBA", icon_rgba.size, rgb + (255,))
    solid.putalpha(icon_rgba.split()[3])
    return solid


def _load_icon(path, box):
    try:
        ic = Image.open(path).convert("RGBA")
    except (OSError, ValueError):
        return None
    s = min(box / ic.width, box / ic.height)
    ic = ic.resize((max(1, round(ic.width * s)), max(1, round(ic.height * s))), Image.LANCZOS)
    pad = Image.new("RGBA", (box, box), (0, 0, 0, 0))
    pad.paste(ic, ((box - ic.width) // 2, (box - ic.height) // 2), ic)
    return pad


def _wrap_lines(d, text, font, max_w, max_lines=3):
    """Greedy word-wrap `text` to `max_w` pixels using `font`."""
    words, lines, cur = (text or "").split(), [], ""
    for word in words:
        trial = (cur + " " + word).strip()
        if d.textlength(trial, font=font) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
        if len(lines) >= max_lines:
            break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    return lines or [""]


def _disc(img, cx, cy, r, fill, ring, ring_w):
    """Draw a white disc with a colored ring and a soft drop shadow at (cx,cy)."""
    w, h = img.size
    # soft shadow
    sh = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(sh).ellipse([cx - r, cy - r + round(r * 0.10), cx + r, cy + r + round(r * 0.10)],
                               fill=(0, 30, 45, 70))
    img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(max(2, round(r * 0.12)))))
    d = ImageDraw.Draw(img)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill + (255,))
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=ring + (255,), width=ring_w)


def _compose_path(brand, size, title, subtitle, cfg, pcfg, background, icon, accent_rgb):
    """The 'path' layout: title+subtitle top-left, ringed icon disc right, photo band + green divider bottom."""
    w, h = size

    def asset(folder, name):
        return brand.asset(os.path.join(folder, name)) if (brand and name) else None

    if background is None:
        background = asset("backgrounds", pcfg.get("background") or cfg.get("background"))
    img = _background(brand, accent_rgb, w, h, background).copy()

    # photo band across the bottom + the brand-accent divider line at its top edge
    photo_h = float(pcfg.get("photoHeight", 0.333))
    band_top = round(h * (1 - photo_h))
    photo_path = asset("backgrounds", pcfg.get("photo"))
    if photo_path and os.path.isfile(photo_path):
        band = _cover_fit(Image.open(photo_path), w, h - band_top)
        img.alpha_composite(band, (0, band_top))
    else:
        img.alpha_composite(_gradient(w, h - band_top, _mix(accent_rgb, (255, 255, 255), 0.2), accent_rgb),
                            (0, band_top))
    div = _hex(pcfg.get("dividerColor"), accent_rgb)
    dt = max(2, round(h * 0.006))
    ImageDraw.Draw(img).rectangle([0, band_top - dt // 2, w, band_top + dt - dt // 2], fill=div + (255,))

    # ringed icon disc on the right
    ccfg = pcfg.get("circle", {})
    cx, cy = round(w * float(ccfg.get("cx", 0.75))), round(h * float(ccfg.get("cy", 0.315)))
    r = round(w * float(ccfg.get("diameter", 0.27)) / 2)
    _disc(img, cx, cy, r, _hex(ccfg.get("fillColor"), (255, 255, 255)),
          _hex(ccfg.get("ringColor"), _hex(brand.get("palette", {}).get("blue") if brand else None, (83, 155, 210))),
          max(3, round(r * 0.045)))
    ibox = round(r * 1.05)
    icon_rgb = _hex(pcfg.get("iconColor"), (26, 26, 26))
    base_icon = _load_icon(icon, ibox) if icon else None
    if base_icon is not None:
        img.alpha_composite(_tint(base_icon, icon_rgb), (cx - ibox // 2, cy - ibox // 2))
    else:                                              # fallback: title initial in the disc
        d0 = ImageDraw.Draw(img)
        f0 = _font(brand, round(r * 0.9), True)
        t0 = (title or "•").strip()[:1].upper()
        l, tp, rr, b = d0.textbbox((0, 0), t0, font=f0)
        d0.text((cx - (rr - l) / 2 - l, cy - (b - tp) / 2 - tp), t0, font=f0, fill=icon_rgb + (255,))

    # title (navy) + subtitle (accent), left-aligned, clear of the disc
    d = ImageDraw.Draw(img)
    left = round(w * float(pcfg.get("titleLeft", 0.065)))
    max_w = (cx - r) - left - round(w * 0.03)
    tf = _font(brand, round(h * 0.105), True)
    lines = _wrap_lines(d, (title or "").strip(), tf, max_w, max_lines=3)
    lh = round(h * 0.105 * 1.16)
    sub = (subtitle or "").strip()
    sf = _font(brand, round(h * 0.044), False)
    block_h = len(lines) * lh + (round(h * 0.07) if sub else 0)
    ty = max(round(h * 0.12), (band_top - block_h) // 2)
    tcol = _hex(pcfg.get("titleColor"), (0, 62, 81))
    for ln in lines:
        d.text((left, ty), ln, font=tf, fill=tcol + (255,))
        ty += lh
    if sub:
        d.text((left, ty + round(h * 0.015)), sub, font=sf,
               fill=_hex(pcfg.get("subtitleColor"), accent_rgb) + (255,))
    return img


def compose(brand, size, title, background=None, icon=None, accent=None, layout=None, subtitle=None):
    """Return an RGBA cover Image at `size` (w,h). bg/icon are file paths or None (synthesized).

    layout: 'topic' (centered icon, optional title) or 'path' (title-left + ringed icon + photo band).
    Falls back to the brand's cover.layout, then 'topic'.
    """
    w, h = size
    cfg = (brand.get("cover") if brand else None) or {}
    accent_rgb = _hex(accent or (brand.accent if brand else None))
    layout = layout or cfg.get("layout", "topic")
    if layout == "path":
        return _compose_path(brand, size, title, subtitle, cfg, cfg.get("path", {}) or {},
                             background, icon, accent_rgb)

    if background is None and cfg.get("background") and brand:
        background = brand.asset(os.path.join("backgrounds", cfg["background"]))
    img = _background(brand, accent_rgb, w, h, background).copy()

    show_title = cfg.get("title", True)
    # bottom scrim only when text sits over the image (helps legibility on photo/gradient bgs)
    if show_title:
        scrim = _gradient(w, h, (0, 0, 0, 0), (0, 0, 0))
        scrim.putalpha(_gradient(w, h, (0, 0, 0), (0, 0, 0)).split()[0].point(lambda v: int(v * 0.55)))
        img.alpha_composite(scrim)

    def face(sz, bold=True):
        return _font(brand, sz, bold)

    box = round(min(w, h) * float(cfg.get("iconScale", 0.34)))
    icon_y = round(h * (0.20 if h >= w else (0.16 if show_title else 0.30)))
    cx = (w - box) // 2
    base_icon = _load_icon(icon, box) if icon else None
    icol, shcol = cfg.get("iconColor"), cfg.get("iconShadow")
    if base_icon is not None and icol:                 # two-tone: shadow copy offset, then the icon
        off = cfg.get("iconShadowOffset", [12, 14])
        if shcol:
            img.alpha_composite(_tint(base_icon, _hex(shcol)), (cx + int(off[0]), icon_y + int(off[1])))
        img.alpha_composite(_tint(base_icon, _hex(icol)), (cx, icon_y))
    elif base_icon is not None:
        img.alpha_composite(base_icon, (cx, icon_y))
    elif icol:                                         # no icon asset: solid branded tile (two-tone)
        tile = _solid_monogram((title or "•").strip()[:1], box, _hex(icol), lambda s: face(s, True))
        if shcol:
            off = cfg.get("iconShadowOffset", [12, 14])
            img.alpha_composite(_tint(tile, _hex(shcol)), (cx + int(off[0]), icon_y + int(off[1])))
        img.alpha_composite(tile, (cx, icon_y))
    elif show_title or not icon:
        img.alpha_composite(_monogram((title or "•").strip()[:1], box, accent_rgb, lambda s: face(s, True)), (cx, icon_y))

    if not show_title:
        return img

    # title — wrapped, centered, under the icon
    d = ImageDraw.Draw(img)
    fsize = round(h * (0.085 if h >= w else 0.11))
    tf = face(fsize, True)
    avg = d.textlength("n", font=tf) or fsize * 0.5
    wrap = max(8, int((w * 0.86) / avg))
    lines = textwrap.wrap((title or "").strip(), width=wrap)[:3] or [""]
    ty = icon_y + box + round(h * 0.06)
    for ln in lines:
        l, tp, r, b = d.textbbox((0, 0), ln, font=tf)
        x = (w - (r - l)) / 2 - l
        d.text((x + 2, ty + 2), ln, font=tf, fill=(0, 0, 0, 120))      # shadow
        d.text((x, ty), ln, font=tf, fill=(255, 255, 255, 255))
        ty += (b - tp) + round(fsize * 0.28)
    return img


def render_set(brand, out_dir, name, title, background=None, icon=None, accent=None,
               layout=None, subtitle=None, sizes=None):
    """Write <name>.png (cover) + <name>_hero.jpg + <name>_mobile.jpg. Returns the paths."""
    os.makedirs(out_dir, exist_ok=True)
    sizes = sizes or SIZES
    out = {}
    for role, dim in sizes.items():
        im = compose(brand, dim, title, background, icon, accent, layout, subtitle).convert("RGB")
        ext = "png" if role == "cover" else "jpg"
        fn = f"{name}.png" if role == "cover" else f"{name}_{role}.{ext}"
        p = os.path.join(out_dir, fn)
        im.save(p, quality=90)
        out[role] = p
    return out
