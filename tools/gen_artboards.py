#!/usr/bin/env python3
"""Generate .dc.html artboards for the Simulxalive design canvas from data/.

Positions are computed here (deterministically) and injected as literals so the
artboards render identically every time, with no RNG in the browser.
Visual system: Dala (see docs/DESIGN.md) - pure #000 void, Inter, weight-400
display type, amber #ffb829 = human, violet #8052ff = LLM.
"""
import json, math, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
D = json.loads((ROOT / "data" / "axes.json").read_text())
AXES, FAMS = D["axes"], D["families"]

VOID, BONE, ASH, SILVER = "#000000", "#ffffff", "#9a9a9a", "#bdbdbd"
IRIS, SAFFRON = "#8052ff", "#ffb829"
FONT = "'Inter', ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"

HEAD = """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <script src="./support.js"></script>
</head>
<body>
<x-dc>
<helmet>
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@200;400;600;700&display=swap">
  <style>
    body { margin: 0; background: #000000; }
    a { color: #ffb829; text-decoration: none; }
    a:hover { color: #ffffff; }
  </style>
</helmet>
"""
TAIL = """</x-dc>
<script data-dc-script data-props='{"$preview":{"width":%d,"height":%d}}'>
class Component extends DCLogic {}
</script>
</body>
</html>
"""

def frame(inner, w, h):
    return (f'<div style="width: {w}px; height: {h}px; background: {VOID}; position: relative; '
            f'overflow: hidden; font-family: {FONT}; color: {BONE};">\n{inner}\n</div>\n')

def header(eyebrow, title, standfirst, note=""):
    n = (f'<p style="margin: 0; font-size: 14px; font-weight: 200; line-height: 1.5; color: {ASH}; '
         f'max-width: 380px;">{note}</p>') if note else ""
    return f"""  <div style="display: flex; align-items: flex-end; justify-content: space-between; gap: 60px; padding: 60px 80px 0 80px;">
    <div style="display: flex; flex-direction: column; gap: 18px; max-width: 720px;">
      <span style="font-size: 14px; font-weight: 600; letter-spacing: 0.35px; text-transform: uppercase; color: {SAFFRON};">{eyebrow}</span>
      <h2 style="margin: 0; font-size: 48px; font-weight: 400; line-height: 1.1; letter-spacing: -1.68px; color: {BONE}; text-wrap: balance;">{title}</h2>
      <p style="margin: 0; font-size: 18px; font-weight: 200; line-height: 1.5; color: {SILVER}; max-width: 620px;">{standfirst}</p>
    </div>
{n}
  </div>
"""

def tri(x, y, s, rot=0.0):
    pts = []
    for k in range(3):
        a = rot + k * 2.0943951
        pts.append(f"{x + s * math.sin(a):.1f},{y - s * math.cos(a):.1f}")
    return " ".join(pts)

EW = {"strong": 1.0, "mixed": 0.7, "contested": 0.4}
def esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

# ---------------------------------------------------------------- constellation
def constellation():
    W, H = 1440, 1060
    VB_W, VB_H = 1280, 660
    fams = sorted(FAMS.items(), key=lambda kv: kv[1]["order"])
    by_fam = {k: [a for a in AXES if a["family"] == k] for k, _ in fams}

    centres = {}
    for i, (key, _) in enumerate(fams):
        th = -1.15 + i * (2.30 / 6)
        centres[key] = (300 - 150 * math.cos(th), 330 + 292 * math.sin(th),
                        980 + 150 * math.cos(th), 330 + 292 * math.sin(th))

    nodes, links, spokes = [], [], []
    for key, _ in fams:
        hx, hy, ax, ay = centres[key]
        grp = by_fam[key]
        for j, a in enumerate(grp):
            ang = (j / max(len(grp), 1)) * 6.2831853 + len(key)
            rad = 20 + (j % 3) * 11
            nhx, nhy = hx + rad * math.cos(ang) * 1.25, hy + rad * math.sin(ang)
            nax, nay = ax - rad * math.cos(ang) * 1.25, ay + rad * math.sin(ang)
            sz = 4.2 + EW[a["evidence"]] * 3.0
            nodes.append((tri(nhx, nhy, sz, ang), SAFFRON))
            nodes.append((tri(nax, nay, sz, ang + 1.0), IRIS))
            spokes.append((nhx, nhy, hx, hy, SAFFRON))
            spokes.append((nax, nay, ax, ay, IRIS))
            mid = (nhy + nay) / 2
            cy = 330 + (mid - 330) * 0.26
            links.append({
                "d": f"M {nhx:.1f} {nhy:.1f} Q 640 {cy:.1f} {nax:.1f} {nay:.1f}",
                "w": f"{0.5 + a['convergence'] * 2.0:.2f}",
                "o": f"{0.10 + a['convergence'] * 0.55:.2f}",
                "dash": "none" if a["robustness"] >= 0.45 else "5 5",
            })

    parts = []
    for x1, y1, x2, y2, c in spokes:
        parts.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                     f'stroke="{c}" stroke-width="0.7" opacity="0.20"></line>')
    for L in links:
        parts.append(f'<path d="{L["d"]}" fill="none" stroke="{BONE}" stroke-width="{L["w"]}" '
                     f'opacity="{L["o"]}" stroke-dasharray="{L["dash"]}"></path>')
    for pts, c in nodes:
        parts.append(f'<polygon points="{pts}" fill="none" stroke="{c}" stroke-width="1.3" opacity="0.92"></polygon>')
    for key, meta in fams:
        hx, hy, ax, ay = centres[key]
        parts.append(f'<text x="{hx - 62:.0f}" y="{hy - 46:.0f}" text-anchor="start" fill="{SAFFRON}" '
                     f'font-size="10" font-weight="600" letter-spacing="0.35" font-family="{FONT}">'
                     f'{meta["label"].upper()}</text>')
        parts.append(f'<text x="{ax + 62:.0f}" y="{ay - 46:.0f}" text-anchor="end" fill="{IRIS}" '
                     f'font-size="10" font-weight="600" letter-spacing="0.35" font-family="{FONT}">'
                     f'{meta["label"].upper()}</text>')
    parts.append(f'<text x="150" y="640" text-anchor="middle" fill="{ASH}" font-size="11" '
                 f'font-weight="600" letter-spacing="0.35" font-family="{FONT}">HUMAN LITERATURE</text>')
    parts.append(f'<text x="1130" y="640" text-anchor="middle" fill="{ASH}" font-size="11" '
                 f'font-weight="600" letter-spacing="0.35" font-family="{FONT}">MODEL LITERATURE</text>')
    svg = (f'  <div style="padding: 36px 80px 0 80px;">\n'
           f'    <svg viewBox="0 0 {VB_W} {VB_H}" width="{VB_W}" height="{VB_H}" role="img" '
           f'aria-label="Bipartite constellation linking 28 human findings to their model counterparts">\n'
           + "\n".join("      " + p for p in parts) + "\n    </svg>\n  </div>\n")

    def key_item(sw, dash, label):
        return (f'<div style="display: flex; align-items: center; gap: 12px;">'
                f'<svg width="34" height="8" aria-hidden="true"><line x1="0" y1="4" x2="34" y2="4" '
                f'stroke="{BONE}" stroke-width="{sw}" stroke-dasharray="{dash}" opacity="0.8"></line></svg>'
                f'<span style="font-size: 12px; font-weight: 200; color: {ASH};">{label}</span></div>')

    legend = f"""  <div style="display: flex; align-items: center; gap: 36px; padding: 24px 80px 0 80px; flex-wrap: wrap;">
    <div style="display: flex; align-items: center; gap: 12px;">
      <svg width="14" height="14" aria-hidden="true"><polygon points="{tri(7, 7, 6)}" fill="none" stroke="{SAFFRON}" stroke-width="1.3"></polygon></svg>
      <span style="font-size: 12px; font-weight: 200; color: {SILVER};">Human finding</span>
    </div>
    <div style="display: flex; align-items: center; gap: 12px;">
      <svg width="14" height="14" aria-hidden="true"><polygon points="{tri(7, 7, 6)}" fill="none" stroke="{IRIS}" stroke-width="1.3"></polygon></svg>
      <span style="font-size: 12px; font-weight: 200; color: {SILVER};">Model finding</span>
    </div>
    {key_item("2.4", "none", "Strong match, holds under rewording")}
    {key_item("2.4", "5 5", "Strong match, collapses under rewording")}
    {key_item("0.7", "none", "Weak match")}
  </div>
"""
    inner = (header("Plate I &mdash; the map",
                    "Two literatures, one set of instruments.",
                    "Each spoke is a construct measured on both sides. The curve between a pair carries the size of the match; a broken curve means the match does not survive trivial rewording of the task.",
                    "Node size follows evidence strength: replicated across independent labs, replicated with caveats, or directly contested.")
             + svg + legend)
    return frame(inner, W, H) + TAIL % (W, H)


def wrap(text, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if len(t) > width and cur:
            lines.append(cur); cur = w
        else:
            cur = t
    if cur:
        lines.append(cur)
    return lines

def tick_labels(x0, x1, y, vals, fmt="{:g}"):
    out = []
    for v in vals:
        x = x0 + (x1 - x0) * v
        out.append(f'<text x="{x:.0f}" y="{y}" text-anchor="middle" fill="{ASH}" font-size="10" '
                   f'font-weight="600" letter-spacing="0.35" font-family="{FONT}">{fmt.format(v)}</text>')
    return out

# ------------------------------------------------------------------ divergence
def divergence():
    W, H = 1440, 1150
    VB_W, VB_H = 1280, 762
    rows = sorted(AXES, key=lambda a: -a["convergence"])
    X0, X1 = 340, 1000
    parts = []
    for v in (0, 0.25, 0.5, 0.75, 1.0):
        x = X0 + (X1 - X0) * v
        parts.append(f'<line x1="{x:.0f}" y1="48" x2="{x:.0f}" y2="724" stroke="#1c1c1c" stroke-width="1"></line>')
    parts += tick_labels(X0, X1, 38, (0, 0.25, 0.5, 0.75, 1.0))
    parts.append(f'<text x="{X1:.0f}" y="22" text-anchor="end" fill="{SAFFRON}" font-size="10" '
                 f'font-weight="600" letter-spacing="0.35" font-family="{FONT}">HUMAN BASELINE</text>')
    for i, a in enumerate(rows):
        y = 64 + i * 24
        xa = X0 + (X1 - X0) * a["convergence"]
        parts.append(f'<text x="300" y="{y + 4}" text-anchor="end" fill="{SILVER}" font-size="11.5" '
                     f'font-weight="200" font-family="{FONT}">{esc(a["label"])}</text>')
        parts.append(f'<line x1="{xa:.0f}" y1="{y}" x2="{X1}" y2="{y}" stroke="{BONE}" stroke-width="1" opacity="0.22"></line>')
        parts.append(f'<circle cx="{X1}" cy="{y}" r="4" fill="{SAFFRON}"></circle>')
        parts.append(f'<circle cx="{xa:.0f}" cy="{y}" r="4.5" fill="{IRIS}"></circle>')
        parts.append(f'<text x="1030" y="{y + 4}" fill="{ASH}" font-size="9.5" font-weight="600" '
                     f'letter-spacing="0.35" font-family="{FONT}">{FAMS[a["family"]]["label"].upper()}</text>')
        parts.append(f'<text x="1250" y="{y + 4}" text-anchor="end" fill="{BONE}" font-size="12" '
                     f'font-weight="400" font-family="{FONT}" style="font-variant-numeric: tabular-nums;">'
                     f'{a["convergence"]:.2f}</text>')
    svg = (f'  <div style="padding: 30px 80px 0 80px;">\n    <svg viewBox="0 0 {VB_W} {VB_H}" width="{VB_W}" '
           f'height="{VB_H}" role="img" aria-label="Distance from the human baseline for 28 constructs">\n'
           + "\n".join("      " + q for q in parts) + "\n    </svg>\n  </div>\n")
    legend = f"""  <div style="display: flex; align-items: center; gap: 36px; padding: 18px 80px 0 80px;">
    <div style="display: flex; align-items: center; gap: 12px;">
      <svg width="12" height="12" aria-hidden="true"><circle cx="6" cy="6" r="4" fill="{SAFFRON}"></circle></svg>
      <span style="font-size: 12px; font-weight: 200; color: {SILVER};">Human baseline, fixed at 1.00 by definition</span>
    </div>
    <div style="display: flex; align-items: center; gap: 12px;">
      <svg width="12" height="12" aria-hidden="true"><circle cx="6" cy="6" r="4.5" fill="{IRIS}"></circle></svg>
      <span style="font-size: 12px; font-weight: 200; color: {SILVER};">Where the model actually lands</span>
    </div>
    <span style="font-size: 12px; font-weight: 200; color: {ASH};">The bar between them is the gap that remains.</span>
  </div>
"""
    inner = (header("Plate II &mdash; the gap",
                    "How far the model still is, construct by construct.",
                    "Every row is one instrument. The amber point is the human result the model is being measured against; the violet point is where it lands.",
                    "Ordered by closeness. The four constructs at the bottom are not behaviour at all &mdash; they are the machine.")
             + svg + legend)
    return frame(inner, W, H) + TAIL % (W, H)

# ------------------------------------------------------------------- fragility
def fragility():
    W, H = 1440, 1000
    VB_W, VB_H = 1280, 648
    X0, X1, Y0, Y1 = 150, 1145, 578, 52
    named = {"turing-3party", "tom-false-belief", "higher-order-tom", "anchoring", "response-variance",
             "strategic-depth", "data-efficiency", "prompt-invariance", "moral-rating-distribution"}
    parts = []
    for v in (0.25, 0.5, 0.75):
        x = X0 + (X1 - X0) * v; y = Y0 + (Y1 - Y0) * v
        w = "1.4" if v == 0.5 else "1"
        c = "#2a2a2a" if v == 0.5 else "#161616"
        parts.append(f'<line x1="{x:.0f}" y1="{Y1}" x2="{x:.0f}" y2="{Y0}" stroke="{c}" stroke-width="{w}"></line>')
        parts.append(f'<line x1="{X0}" y1="{y:.0f}" x2="{X1}" y2="{y:.0f}" stroke="{c}" stroke-width="{w}"></line>')
    parts.append(f'<line x1="{X0}" y1="{Y0}" x2="{X1}" y2="{Y0}" stroke="#2a2a2a" stroke-width="1"></line>')
    parts.append(f'<line x1="{X0}" y1="{Y1}" x2="{X0}" y2="{Y0}" stroke="#2a2a2a" stroke-width="1"></line>')
    for lbl, x, y, anc in (("LOOKS HUMAN, ISN&#39;T", X1 - 8, Y0 - 14, "end"),
                           ("CONVERGENT AND STABLE", X1 - 8, Y1 + 18, "end"),
                           ("DIFFERENT, RELIABLY SO", X0 + 8, Y1 + 18, "start"),
                           ("DIFFERENT AND UNSTABLE", X0 + 8, Y0 - 14, "start")):
        parts.append(f'<text x="{x:.0f}" y="{y:.0f}" text-anchor="{anc}" fill="#3d3d3d" font-size="11" '
                     f'font-weight="600" letter-spacing="0.35" font-family="{FONT}">{lbl}</text>')
    for v in (0, 0.25, 0.5, 0.75, 1.0):
        x = X0 + (X1 - X0) * v; y = Y0 + (Y1 - Y0) * v
        parts.append(f'<text x="{x:.0f}" y="{Y0 + 26}" text-anchor="middle" fill="{ASH}" font-size="10" '
                     f'font-weight="600" font-family="{FONT}">{v:g}</text>')
        parts.append(f'<text x="{X0 - 14}" y="{y + 4:.0f}" text-anchor="end" fill="{ASH}" font-size="10" '
                     f'font-weight="600" font-family="{FONT}">{v:g}</text>')
    parts.append(f'<text x="{(X0 + X1) / 2:.0f}" y="{Y0 + 50}" text-anchor="middle" fill="{SAFFRON}" font-size="11" '
                 f'font-weight="600" letter-spacing="0.35" font-family="{FONT}">CONVERGENCE &#8594;</text>')
    parts.append(f'<text x="{X0 - 52}" y="{(Y0 + Y1) / 2:.0f}" text-anchor="middle" fill="{SAFFRON}" font-size="11" '
                 f'font-weight="600" letter-spacing="0.35" font-family="{FONT}" '
                 f'transform="rotate(-90 {X0 - 52} {(Y0 + Y1) / 2:.0f})">ROBUSTNESS &#8594;</text>')
    flip = 0
    for a in AXES:
        x = X0 + (X1 - X0) * a["convergence"]; y = Y0 + (Y1 - Y0) * a["robustness"]
        s = 4.5 + EW[a["evidence"]] * 3.2
        hot = a["id"] in named
        col = SAFFRON if hot else BONE
        op = "0.95" if hot else "0.45"
        parts.append(f'<polygon points="{tri(x, y, s)}" fill="none" stroke="{col}" stroke-width="1.4" opacity="{op}"></polygon>')
        if hot:
            right = x < 620
            lx = x + (16 if right else -16)
            anc = "start" if right else "end"
            ly = y + (5 if flip % 2 == 0 else -9)
            flip += 1
            parts.append(f'<text x="{lx:.0f}" y="{ly:.0f}" text-anchor="{anc}" fill="{BONE}" font-size="11" '
                         f'font-weight="200" font-family="{FONT}">{esc(a["label"])}</text>')
    svg = (f'  <div style="padding: 30px 80px 0 80px;">\n    <svg viewBox="0 0 {VB_W} {VB_H}" width="{VB_W}" '
           f'height="{VB_H}" role="img" aria-label="Convergence against robustness for 28 constructs">\n'
           + "\n".join("      " + q for q in parts) + "\n    </svg>\n  </div>\n")
    inner = header("Plate III &mdash; the catch",
                   "The closest matches are the most fragile ones.",
                   "Convergence across the bottom, robustness up the side. If closeness to human behaviour were a real property of these systems, the cloud would run bottom-left to top-right. It runs the other way.",
                   "Nine constructs labelled. Triangle size follows evidence strength.") + svg
    return frame(inner, W, H) + TAIL % (W, H)

# ------------------------------------------------------------------- protocols
def protocols_plate():
    W, H = 1440, 1120
    P = json.loads((ROOT / "data" / "protocols.json").read_text())["protocols"]
    VB_W, VB_H = 1280, 756
    X0, X1 = 600, 1180
    parts = []
    for v in (0, 50, 100):
        x = X0 + (X1 - X0) * (v / 100)
        parts.append(f'<line x1="{x:.0f}" y1="26" x2="{x:.0f}" y2="{40 + len(P) * 100}" stroke="#1c1c1c" stroke-width="1"></line>')
        parts.append(f'<text x="{x:.0f}" y="16" text-anchor="middle" fill="{ASH}" font-size="10" '
                     f'font-weight="600" font-family="{FONT}">{v}%</text>')
    for i, pr in enumerate(P):
        y = 62 + i * 100
        parts.append(f'<text x="0" y="{y}" fill="{BONE}" font-size="18" font-weight="400" '
                     f'font-family="{FONT}">{esc(pr["name"])}</text>')
        for k, line in enumerate(wrap(pr["instrument"], 64)[:2]):
            parts.append(f'<text x="0" y="{y + 22 + k * 16}" fill="{ASH}" font-size="11.5" font-weight="200" '
                         f'font-family="{FONT}">{esc(line)}</text>')
        parts.append(f'<text x="0" y="{y + 62}" fill="#6a6a6a" font-size="10" font-weight="600" '
                     f'letter-spacing="0.35" font-family="{FONT}">{esc(pr["metric"]).upper()}</text>')
        xh = X0 + (X1 - X0) * (pr["human"] / 100)
        xa = X0 + (X1 - X0) * (pr["ai"] / 100)
        parts.append(f'<line x1="{min(xh, xa):.0f}" y1="{y + 6}" x2="{max(xh, xa):.0f}" y2="{y + 6}" '
                     f'stroke="{BONE}" stroke-width="1" opacity="0.25"></line>')
        parts.append(f'<circle cx="{xh:.0f}" cy="{y + 6}" r="5" fill="{SAFFRON}"></circle>')
        parts.append(f'<circle cx="{xa:.0f}" cy="{y + 6}" r="5" fill="{IRIS}"></circle>')
        ha = "end" if xh > xa else "start"
        aa = "start" if xh > xa else "end"
        parts.append(f'<text x="{xh + (-10 if xh > xa else 10):.0f}" y="{y + 10}" text-anchor="{ha}" fill="{SAFFRON}" '
                     f'font-size="15" font-weight="400" font-family="{FONT}" '
                     f'style="font-variant-numeric: tabular-nums;">{pr["human"]:g}</text>')
        parts.append(f'<text x="{xa + (10 if xh > xa else -10):.0f}" y="{y + 10}" text-anchor="{aa}" fill="{IRIS}" '
                     f'font-size="15" font-weight="400" font-family="{FONT}" '
                     f'style="font-variant-numeric: tabular-nums;">{pr["ai"]:g}</text>')
        parts.append(f'<text x="{X0}" y="{y + 34}" fill="{IRIS}" font-size="10" font-weight="600" '
                     f'letter-spacing="0.35" font-family="{FONT}">{esc(pr["ai_label"]).upper()}</text>')
        for k, line in enumerate(wrap(pr["note"], 72)[:2]):
            parts.append(f'<text x="{X0}" y="{y + 56 + k * 16}" fill="#6a6a6a" font-size="11.5" font-weight="200" '
                         f'font-family="{FONT}">{esc(line)}</text>')
    svg = (f'  <div style="padding: 30px 80px 0 80px;">\n    <svg viewBox="0 0 {VB_W} {VB_H}" width="{VB_W}" '
           f'height="{VB_H}" role="img" aria-label="Seven protocols run on humans and on models">\n'
           + "\n".join("      " + q for q in parts) + "\n    </svg>\n  </div>\n")
    inner = header("Plate IV &mdash; the runs",
                   "The same protocol, administered to both.",
                   "Only studies that report a number for people and for the model on one scale appear here. Amber is the human result; violet is the model on the identical instrument.",
                   "Where the violet point sits to the right of the amber one, the model is not imitating people &mdash; it is outperforming them at being taken for one.") + svg
    return frame(inner, W, H) + TAIL % (W, H)

# --------------------------------------------------------------------- verdict
def verdict():
    W, H = 1440, 860
    blocks = [
        (SAFFRON, "What the evidence supports",
         "Behaviour that reads as human can be produced by a machine that is nothing like a brain &mdash; three to five orders of magnitude hungrier for language data, far hungrier for power, and unstable under rewording that would not trouble a person. Behaviour, at least the behaviour we know how to measure, is substrate-independent. That is a genuine and surprising result."),
        (IRIS, "What it does not support",
         "Nothing here bears on whether this universe is computed. A system passing for human tells you about the difficulty of the test, not about the nature of the tester. Energy-based arguments place this universe&#39;s own simulation beyond reach under its own physics, and a Bayesian treatment of the simulation argument puts the probability below 50%."),
        (ASH, "What would change the reading",
         "A model that reproduces the human response distribution rather than its mean, survives adversarial reformatting, and does it on a human data and power budget. Until then the fragility column, not the convergence column, is where the argument actually lives."),
    ]
    cards = "\n".join(
        f"""    <div style="display: flex; flex-direction: column; gap: 12px; max-width: 560px;">
      <span style="font-size: 12px; font-weight: 600; letter-spacing: 0.35px; text-transform: uppercase; color: {c};">{t}</span>
      <p style="margin: 0; font-size: 17px; font-weight: 200; line-height: 1.5; color: {SILVER};">{b}</p>
    </div>""" for c, t, b in blocks)
    inner = f"""  <div style="display: flex; gap: 96px; padding: 96px 80px 0 80px;">
    <div style="display: flex; flex-direction: column; gap: 24px; width: 520px; flex-shrink: 0;">
      <span style="font-size: 14px; font-weight: 600; letter-spacing: 0.35px; text-transform: uppercase; color: {SAFFRON};">Plate V &mdash; the reading</span>
      <h2 style="margin: 0; font-size: 48px; font-weight: 400; line-height: 1.1; letter-spacing: -1.68px; color: {BONE}; text-wrap: balance;">Convergence is not evidence of simulation.</h2>
      <p style="margin: 0; font-size: 18px; font-weight: 200; line-height: 1.5; color: {SILVER};">Behaviour is converging. Internal representations are converging too, which is the genuinely unexpected part. The machine underneath is not converging at all. That combination has a clear reading, and it is not the one the question usually invites.</p>
    </div>
    <div style="display: flex; flex-direction: column; gap: 36px;">
{cards}
    </div>
  </div>
  <div style="position: absolute; left: 80px; bottom: 60px; display: flex; gap: 60px; align-items: baseline;">
    <span style="font-size: 12px; font-weight: 600; letter-spacing: 0.35px; text-transform: uppercase; color: #6a6a6a;">28 constructs &middot; 7 paired protocols &middot; 61 sources</span>
    <span style="font-size: 12px; font-weight: 200; color: #6a6a6a;">Convergence and robustness are our codings of the cited literature, not figures reported by the papers. The rubric ships with the data.</span>
  </div>
"""
    return frame(inner, W, H) + TAIL % (W, H)

if __name__ == "__main__":
    for name, fn in (("Constellation", constellation), ("Divergence", divergence),
                     ("Fragility", fragility), ("Protocols", protocols_plate), ("Verdict", verdict)):
        (ROOT / f"{name}.dc.html").write_text(HEAD + fn())
        print(f"{name}.dc.html")
