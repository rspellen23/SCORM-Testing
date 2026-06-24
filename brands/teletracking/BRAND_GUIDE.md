# TeleTracking — Brand Guide (logo specifications)

> Human-readable brand rules for Nova Course Builder deliverables. The
> machine config the builder actually consumes is [`brand.json`](brand.json)
> (palette, fonts, logo file pointer, cover geometry); this doc captures the
> usage rules that config can't encode.
>
> **Source of truth:** `TeleTracking_BrandBook_v1.1.pdf`, §Visual Identity
> (pp. 11–16), in `…/Branding Resources/OneDrive_2_6-4-2026/`. Logo asset
> sets + the Identity QRG live in the same `Branding Resources/` folder.
> Where this doc and `brand.json` disagree on a value, the Brand Book wins —
> open an issue rather than silently editing.

---

## Logo anatomy

The TeleTracking primary logo ("signature" logo) is **three elements**:

- **"Tele"** — set in **ITC Eras Bold**
- **"Tracking"** — set in **ITC Eras Medium**
- the **swoosh**

These are locked together. Do not recreate, re-typeset, or separate them —
always use an approved logo file.

## Clearspace

Allow the logo to "breathe." Required clear/open space around the logo is
**proportional, defined by the lowercase "a"** of the TeleTracking wordmark:
take the "a" from the logo and adhere it to each exterior edge to establish
the minimum margin on all sides. Nothing (text, graphics, edges) may
encroach inside that zone.

## Minimum size

| Application | Minimum width |
|---|---|
| **Print** | **1 inch** wide |
| **Web / digital** | **100 px** wide |

Below these sizes, switch to the **monogram (TMark)** instead of the full
wordmark (see below).

## Approved logos & background rules

White is always the **preferred** background. Secondary (one-color) logos
may go on colored backgrounds **only** with sufficient contrast for
legibility and ADA compliance — rule of thumb: background at least **3×
darker or lighter** than the logo.

| Logo variant | Approved backgrounds |
|---|---|
| **Primary (two-color) logo** | White |
| **White secondary logo** | Black, Green, Navy |
| **Green secondary logo** | Black, White |
| **Black secondary logo** | White, Light Grey |
| **White & Grey secondary logo** | Black, Navy |

> **Builder note:** on the Nova course dark/navy topbar, use the **All-White
> wordmark** — the default colored/black logo is invisible on navy (already
> caught and fixed in the builder; see brand-assets memory). The on-disk
> default `brands/teletracking/Logo.png` is the asset pointed to by
> `brand.json → "logo"`.

## Monogram (TMark)

The TMark is the compact mark for **digital/web (and print) uses where the
primary wordmark can't meet the minimum-size rule**. The **two-color**
monogram is preferred; three secondary one-color monograms exist. Same usage
rules as the primary logo apply. (Monogram-on-merch = internal use only —
not enough external brand recognition yet.) A **green T-mark** makes a good
favicon/compact mark.

## Alignment of accompanying text

Because of the logo's asymmetric shape:

- **Single line** (tagline / hashtag / URL) beneath the logo → **centered
  between the edge of the "T" and the "G."**
- **Multiple lines** of content beneath the logo → **left-justified, flush
  with the stem of the "T."**

## Misuse — do NOT

The Brand Book's misuse examples (not exhaustive):

- ❌ Resize, move, or recolor the **swoosh**
- ❌ Place on **complex or low-contrast** backgrounds
- ❌ Add **gradients or effects**
- ❌ Change the **approved typeface/font**
- ❌ **Stretch or condense** the logo
- ❌ **Recolor** the logo
- ❌ **Box in / contain** the logo in any shape
- ❌ **Rotate** the logo

## Brand extensions

Creating new logos is discouraged. Only the Brand Book's listed brand-
extension logos are approved; each is the TeleTracking logo (left) bound to
the extension mark (right) and the pair becomes a single, inseparable logo.

---

## Related

- Palette + font hexes/families and on-disk asset locations:
  `reference_teletracking_brand_assets.md` in project memory.
- Written **voice** standard (2nd person, active voice, plain professional):
  [`../../templates/AUTHORING_GUIDE.md`](../../templates/AUTHORING_GUIDE.md) §5.
- Machine config consumed by the builder: [`brand.json`](brand.json).
