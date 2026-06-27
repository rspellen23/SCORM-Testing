# TeleTracking Brand Standards (kit reference)

> Source of truth for the TeleTracking brand profile used by course-builder.
> Reconciled to the **2026 official PowerPoint template** on 2026-06-25.
> Edit `brand.json` for machine-readable values; this file is the human rationale.

## Provenance

Three official PowerPoint templates were ingested from `~/KB-Intake/`:

| File | What it is | Role here |
|------|-----------|-----------|
| `2026.01_TeleTracking Template.pptx` | The current corporate template — 48 named 16:9 layouts, 1 master | **Authoritative** for palette, fonts, layout language, logos |
| `2026.01_TelePlatformDeck.pptx` | A large product/platform content deck (77 slides) | Confirms the 2026 theme (identical palette + fonts) |
| `2024.01_TGSTemplate.potx` | The prior (2024) corporate template — 20 layouts | The source our **earlier** brand.json was built from |

Our `brand.json` previously matched the **2024** template. As of 2026-06-25 it is
reconciled to the **2026** standard (palette refreshed; fonts deliberately kept — see below).

## Palette

Theme colors come from the 2026 template's `clrScheme`. Engine roles
(`primary/secondary/tertiary/dark`) map to these palette keys.

| Role / key | 2026 hex (current) | 2024 hex (prior) | Notes |
|-----------|--------------------|------------------|-------|
| green (primary) | `#1EB16A` | `#1EB16A` | **TeleGreen.** 2026 theme stores `#1EB169` — a 1/255 re-export rounding; we keep the canonical `#1EB16A`. |
| teal (secondary) | `#00A5A7` | `#069696` | refreshed |
| blue (tertiary) | `#63ACDB` | `#539BD2` | refreshed |
| navy (dk2) | `#003E51` | `#003E51` | unchanged |
| deepNavy (dk1) | `#0B2C37` | `#0B2C37` | unchanged; header/closing background |
| yellow / gold | `#F1C700` | `#ECBD00` | refreshed |
| orange | `#F69000` | `#F27D05` | refreshed |
| red | `#CB4B3C` | `#BD362F` | refreshed |
| light (lt2) | `#EDF0F0` | — | light-grey surface (new in 2026) |
| accentGreen | `#4EE89E` | `#4EE89E` | bright mint, our addition (not in the official theme) |

Note: the pre-rendered ribbon art in `transitions/*.png` still carries the 2024
hues; it is decorative and was not regenerated. Regenerate if exact ribbon-color
match to the 2026 accents is ever needed.

## Fonts

**Kept: Open Sans** (`head: Open Sans Condensed`, `body: Open Sans`).

The 2026 theme's `fontScheme` lists **Aptos Display / Aptos** — but Aptos is also
Microsoft Office's current *default* theme font, so its presence is ambiguous: it
may be an intentional refresh, or simply the unset Office default in a deck where
only colors were customized. Open Sans is TeleTracking's long-documented brand
font and the deliberate choice in the 2024 template, so the kit keeps Open Sans.

> **OPEN QUESTION for the brand team:** did TeleTracking officially move to Aptos
> in 2026? If yes, switch `fonts` in `brand.json` to Aptos Display / Aptos.

## Logos

The official wordmark, both variants, extracted from the 2026 template into `logos/`:

| File | Variant | Use |
|------|---------|-----|
| `logos/logo-white.svg` | white vector wordmark | dark backgrounds (vector, best quality) |
| `logos/logo-white.png` | white raster wordmark | dark backgrounds (raster) |
| `logos/logo-color.svg` | green+dark vector wordmark | light backgrounds |
| `logos/logo-color.png` | green+dark raster wordmark | light backgrounds |
| `Logo.png` | white raster wordmark (1531×331) | **manifest `logo`** — used by the slide engine's header mark and HTML course render |

The slide engine places a raster logo via `add_picture` (so `brand.json.logo`
stays a PNG). The header mark appears top-right on every header-band layout and
centered at the bottom of the `closing` layout.

## Slide format

16:9, **13.33in × 7.50in** — matches the engine's canvas exactly (no rescaling).

## Layout language

Engine layouts (`slide_layouts.LAYOUTS`, 14) vs. the official template's 48 layouts.

**Have, aligned:** divider · agenda · process (≈ Steps/Processes) · comparison
(≈ Two/Three Content) · timeline · infographic · cards (≈ 4 Content Blocks) ·
quote · statement · bullets (≈ List) · image / imagetext (≈ Content+Image) ·
chart · closing.

**Added 2026-06-25** to match the template: **`agenda`** (numbered table of
contents) and **`closing`** (thank-you with centered wordmark).

**Official layouts not yet generalized into the engine (backlog):**
- **Section Header** — numbered section break (a divider variant)
- **Cycles (dark/light)** — circular/cyclical process (vs. our linear `process`)
- **Org Chart 1 / 2** — hierarchy diagram
- **Steps/Processes** info-left / info-right / numbered variants (we have one `process`)
- **Dark/Light mode** — the official template offers most layouts in BOTH dark and
  light; our layouts are light-bodied with a dark header. A `theme: dark|light`
  content flag across layouts would mirror this. (Cross-cutting; staged.)
- **Agenda/Divider with picture**, **Presenters/Team**, **Citations**, **Cycles**.

Source templates remain in `~/KB-Intake/` for further extraction.
