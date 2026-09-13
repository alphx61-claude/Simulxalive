#!/usr/bin/env bash
# Rebuild the design canvas from the artboard sources and publish-ready file.
# Requires Claude Code's `design` skill payload; SKILL_DIR points at its base directory.
set -euo pipefail
cd "$(dirname "$0")/.."
: "${SKILL_DIR:?set SKILL_DIR to the design skill base directory}"

python3 tools/gen_artboards.py

node "$SKILL_DIR/seed-canvas.mjs" \
  --template "$SKILL_DIR/payload.template.html" \
  --out simulxalive-atlas.html \
  --title "Simulxalive Atlas" \
  --artboard Main.dc.html \
  --artboard Constellation.dc.html \
  --artboard Divergence.dc.html \
  --artboard Fragility.dc.html \
  --artboard Protocols.dc.html \
  --artboard Verdict.dc.html \
  --canvas canvas.json

node "$SKILL_DIR/seed-canvas.mjs" --check simulxalive-atlas.html
