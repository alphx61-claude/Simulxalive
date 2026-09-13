#!/usr/bin/env python3
"""Render ROADMAP.md and the tracking page from docs/roadmap.json.

docs/roadmap.json is the single source of truth. Both outputs are generated;
edit the JSON, never the outputs. Visual system: Dala (docs/DESIGN.md).
"""
import json, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
R = json.loads((ROOT / "docs" / "roadmap.json").read_text())
PHASES = R["phases"]

VOID, BONE, ASH, SILVER = "#000000", "#ffffff", "#9a9a9a", "#bdbdbd"
IRIS, SAFFRON, MUTED = "#8052ff", "#ffb829", "#6a6a6a"
STATUS = {"done": SAFFRON, "next": IRIS, "planned": MUTED}

def counts(p):
    return sum(1 for m in p["milestones"] if m["done"]), len(p["milestones"])

TOT = sum(len(p["milestones"]) for p in PHASES)
DONE = sum(c for c, _ in map(counts, PHASES))

def esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

# ------------------------------------------------------------------ markdown
def markdown():
    L = [f"# {R['project']} — roadmap", "",
         "<!-- Generated from docs/roadmap.json by tools/gen_roadmap.py. Do not edit. -->", "",
         R["premise"], "",
         f"**{DONE} of {TOT} milestones complete.**", "", "## Decisions taken", ""]
    for d in R["decisions"]:
        L += [f"- **{d['q']}** — {d['a']}"]
    L += ["", "## Phases", ""]
    for p in PHASES:
        c, n = counts(p)
        L += [f"### {p['id']}. {p['name']} — _{p['status']}_  ({c}/{n})", "", p["goal"], ""]
        for m in p["milestones"]:
            L += [f"- [{'x' if m['done'] else ' '}] {m['t']}"]
        if p.get("exit"):
            L += ["", f"**Done when:** {p['exit']}"]
        L += [""]
    L += ["## Invariants", "",
          "Breaking these makes the project worthless, not merely untidy.", ""]
    for i, inv in enumerate(R["invariants"], 1):
        L += [f"{i}. {inv}"]
    return "\n".join(L) + "\n"

# ---------------------------------------------------------------------- page
def page():
    blocks = []
    for p in PHASES:
        c, n = counts(p)
        col = STATUS[p["status"]]
        pct = (c / n * 100) if n else 0
        items = "\n".join(
            f'      <li style="display: flex; gap: 14px; align-items: baseline;">'
            f'<span aria-hidden="true" style="color: {SAFFRON if m["done"] else MUTED}; font-size: 13px; flex-shrink: 0;">'
            f'{"&#10003;" if m["done"] else "&#9675;"}</span>'
            f'<span style="color: {SILVER if m["done"] else ASH};">{esc(m["t"])}</span></li>'
            for m in p["milestones"])
        exit_line = (f'<p class="exit"><span class="k">Done when</span> {esc(p["exit"])}</p>'
                     if p.get("exit") else "")
        blocks.append(f"""  <section class="phase">
    <div class="phase-head">
      <span class="num" style="color: {col};">{p['id']}</span>
      <div class="phase-title">
        <h2>{esc(p['name'])}</h2>
        <span class="status" style="color: {col};">{p['status']} &middot; {c}/{n}</span>
      </div>
    </div>
    <div class="track"><span style="width: {pct:.0f}%; background: {col};"></span></div>
    <p class="goal">{esc(p['goal'])}</p>
    <ul class="ms">
{items}
    </ul>
    {exit_line}
  </section>""")

    decisions = "\n".join(
        f'    <div class="dec"><span class="k">{esc(d["q"])}</span><p>{esc(d["a"])}</p></div>'
        for d in R["decisions"])
    invariants = "\n".join(
        f'    <li><span class="n">{i}</span><p>{esc(inv)}</p></li>'
        for i, inv in enumerate(R["invariants"], 1))

    return f"""<title>Simulxalive Roadmap</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@200;400;600;700&display=swap">
<style>
  :root {{
    color-scheme: dark;
    --void: {VOID}; --bone: {BONE}; --ash: {ASH}; --silver: {SILVER};
    --iris: {IRIS}; --saffron: {SAFFRON}; --muted: {MUTED}; --hair: #1c1c1c;
  }}
  * {{ box-sizing: border-box; min-width: 0; }}
  html, body {{ max-width: 100%; overflow-x: clip; }}
  body {{
    background: var(--void); color: var(--bone); margin: 0;
    font-family: 'Inter', ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
    -webkit-font-smoothing: antialiased;
  }}
  .wrap {{
    max-width: 1080px; width: 100%; margin: 0 auto;
    padding-inline: 24px; padding-block: 72px 96px; overflow-wrap: break-word;
  }}
  a {{ color: var(--saffron); text-decoration: none; }}
  a:hover {{ color: var(--bone); }}
  .k {{
    font-size: 12px; font-weight: 600; letter-spacing: 0.35px; text-transform: uppercase;
    color: var(--saffron);
  }}
  h1 {{
    margin: 18px 0 0; font-size: clamp(40px, 7.4vw, 78px); font-weight: 400;
    line-height: 1.06; letter-spacing: -0.04em; text-wrap: balance;
  }}
  .premise {{
    margin: 24px 0 0; font-size: clamp(17px, 2.2vw, 20px); font-weight: 200;
    line-height: 1.5; color: var(--silver); max-width: 30em;
  }}
  .meter {{ display: flex; flex-direction: column; gap: 14px; margin-top: 48px; max-width: 520px; }}
  .meter .fig {{
    font-size: clamp(34px, 6vw, 56px); font-weight: 400; letter-spacing: -0.03em;
    line-height: 1; font-variant-numeric: tabular-nums;
  }}
  .meter .fig span {{ color: var(--muted); }}
  .track {{ height: 2px; background: var(--hair); width: 100%; display: block; }}
  .track > span {{ display: block; height: 100%; }}
  .decs {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 36px; margin-top: 96px;
  }}
  .dec p {{ margin: 10px 0 0; font-size: 15px; font-weight: 200; line-height: 1.5; color: var(--silver); }}
  .phases {{ display: flex; flex-direction: column; gap: 72px; margin-top: 96px; }}
  .phase-head {{ display: flex; gap: 24px; align-items: baseline; }}
  .num {{
    font-size: 42px; font-weight: 400; letter-spacing: -0.04em; line-height: 1;
    font-variant-numeric: tabular-nums; flex-shrink: 0; width: 48px;
  }}
  .phase-title {{ display: flex; flex-direction: column; gap: 8px; }}
  .phase h2 {{
    margin: 0; font-size: clamp(24px, 3.4vw, 36px); font-weight: 400;
    line-height: 1.15; letter-spacing: -0.02em;
  }}
  .status {{ font-size: 12px; font-weight: 600; letter-spacing: 0.35px; text-transform: uppercase; }}
  .phase .track {{ margin: 24px 0 0; }}
  .goal {{
    margin: 24px 0 0; font-size: 18px; font-weight: 200; line-height: 1.5;
    color: var(--silver); max-width: 34em;
  }}
  .ms {{ list-style: none; margin: 24px 0 0; padding: 0; display: flex; flex-direction: column; gap: 12px; }}
  .ms li {{ font-size: 15px; font-weight: 200; line-height: 1.5; max-width: 40em; }}
  .exit {{
    margin: 24px 0 0; font-size: 14px; font-weight: 200; line-height: 1.5;
    color: var(--ash); max-width: 40em;
  }}
  .exit .k {{ margin-right: 8px; color: var(--iris); }}
  .inv {{ margin-top: 120px; }}
  .inv ol {{ list-style: none; margin: 36px 0 0; padding: 0; display: flex; flex-direction: column; gap: 24px; }}
  .inv li {{ display: flex; gap: 18px; align-items: baseline; }}
  .inv .n {{
    font-size: 14px; font-weight: 600; color: var(--iris); width: 18px; flex-shrink: 0;
    font-variant-numeric: tabular-nums;
  }}
  .inv p {{ margin: 0; font-size: 16px; font-weight: 200; line-height: 1.5; color: var(--silver); max-width: 40em; }}
  footer {{ margin-top: 96px; font-size: 12px; font-weight: 200; color: var(--muted); line-height: 1.6; }}
  @media (max-width: 560px) {{
    .wrap {{ padding-block: 48px 64px; }}
    .phase-head {{ gap: 14px; }}
    .num {{ font-size: 30px; width: 32px; }}
    .phases {{ gap: 56px; }}
  }}
  @media (prefers-reduced-motion: reduce) {{ * {{ animation: none !important; transition: none !important; }} }}
</style>

<div class="wrap">
  <header>
    <span class="k">{R['project']} &middot; roadmap</span>
    <h1>Where the gap is closing,<br>and where it isn&#39;t.</h1>
    <p class="premise">{esc(R['premise'])} Built over many sessions and generated from the repository, so this is the real state of the work rather than a summary of it.</p>
    <div class="meter">
      <span class="fig">{DONE}<span>/{TOT}</span></span>
      <span class="track"><span style="width: {DONE / TOT * 100:.1f}%; background: {SAFFRON};"></span></span>
      <span style="font-size: 13px; font-weight: 200; color: {ASH};">milestones complete across {len(PHASES)} phases</span>
    </div>
  </header>

  <div class="decs">
{decisions}
  </div>

  <div class="phases">
{chr(10).join(blocks)}
  </div>

  <div class="inv">
    <span class="k">Invariants</span>
    <p class="goal">Breaking these makes the project worthless, not merely untidy.</p>
    <ol>
{invariants}
    </ol>
  </div>

  <footer>
    Generated from <code>docs/roadmap.json</code>. Convergence and robustness scores throughout the project
    are codings of the cited literature against a published rubric, not figures reported by the papers.
  </footer>
</div>
"""

if __name__ == "__main__":
    (ROOT / "ROADMAP.md").write_text(markdown())
    out = ROOT / "dist"; out.mkdir(exist_ok=True)
    (out / "roadmap.html").write_text(page())
    print(f"ROADMAP.md and dist/roadmap.html written - {DONE}/{TOT} milestones")
