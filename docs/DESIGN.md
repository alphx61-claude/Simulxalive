# Visual system

The atlas follows **Dala**: a dark-stage system where pure black is the working
surface, not a fallback.

## Tokens

| Role | Value | Use |
|---|---|---|
| Void | `#000000` | Every surface. No dark-grey panels, ever. |
| Bone | `#ffffff` | Primary text, chart marks |
| Ash | `#9a9a9a` | Secondary text, axis labels |
| Silver | `#bdbdbd` | Body copy |
| Electric Iris | `#8052ff` | **Model** data, the single filled action control, logo |
| Saffron Spark | `#ffb829` | **Human** data, section eyebrows, emphasis |
| Deep Verdant | `#15846e` | Logo gradient stop only |

### Why amber and violet carry the data

The two domains need colors that read as opposite, and Dala already defines amber
against violet as its chromatic tension. The pair validates well past the
colorblind-separation target on a black surface (CVD ΔE 42.0, normal-vision ΔE 45.8,
all-pairs). Deep Verdant is **not** used as a data color — at `#15846e` it falls below
the chroma floor on black and reads as grey.

Since violet doubles as the filled-button color, no plate carries both a CTA and violet
marks: the hero has the only button in the product.

## Type

Inter (substituting PPNeueMontreal), weights 200 / 400 / 600 / 700. Hierarchy comes
from scale and tracking, never weight:

| Role | Size | Weight | Tracking |
|---|---|---|---|
| Display | 78px | 400 | −3.12px |
| Heading | 48px | 400 | −1.68px |
| Body | 18px | 200 | — |
| Eyebrow / nav | 14px | 600 | 0.35px, uppercase |
| Caption / axis | 10–12px | 200 / 600 | — |

All figures use `font-variant-numeric: tabular-nums`.

## Layout

1440px artboards, 1280px content, 80px gutters. Sibling groups use flex/grid with
`gap`. No cards, borders, dividers, shadows or elevation — hierarchy is scale, color
and whitespace on void. Charts are drawn directly onto the void with hairline axes
(`#1c1c1c`–`#2a2a2a`), never inside a panel.

## Chart rules

- One scale per plate; no dual axes.
- Two series maximum (human, model), always with a legend, plus selective direct
  labels — never a number on every mark.
- Grid and axis rules are solid hairlines one shade off the surface, never dashed.
  Dashing is reserved to mean "this match collapses under rewording".
- Mark size encodes evidence strength; it never encodes a second measure.
