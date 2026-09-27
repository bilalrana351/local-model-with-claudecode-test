#!/usr/bin/env bash
# Build report.pdf from report.md, inlining architecture.svg (make-pdf does not load local image files).
set -euo pipefail
cd "$(dirname "$0")"

python3 - <<'EOF'
import re
svg = open("architecture.svg").read()
svg = re.sub(r"<!--.*?-->", "", svg, flags=re.S)
svg = "\n".join(l for l in svg.splitlines() if l.strip())
md = open("report.md").read().replace("<!-- ARCH -->", f'<div class="fig">\n{svg}\n</div>')
open(".report.build.md", "w").write(md)
EOF

"$HOME/.claude/skills/gstack/make-pdf/dist/pdf" generate --quiet --no-confidential --no-chapter-breaks \
  --margins 0.6in --page-size a4 --author "Bilal Rana" \
  --title "Resolving SWE-bench Verified issues with a local coding agent" \
  .report.build.md report.pdf
rm .report.build.md
pdfinfo report.pdf | grep Pages
