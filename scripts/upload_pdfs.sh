#!/usr/bin/env bash
# Mirror the PDFs from the old lab site as assets of the GitHub release "pdfs" (public, unlimited size, served over HTTPS).
# Usage: scripts/upload_pdfs.sh <folder with the PDFs named as in data/papers.json links[].file>
set -euo pipefail
DIR="${1:-work/pdfs}"
REPO="torwager/canlab"
gh release view pdfs -R "$REPO" >/dev/null 2>&1 || gh release create pdfs -R "$REPO" --title "PDF archive" --notes "Full-text PDFs of CANlab publications, mirrored from sites.dartmouth.edu/canlab. Provided for personal, scholarly use; copyright remains with the publishers and authors." --latest=false
have=$(gh release view pdfs -R "$REPO" --json assets --jq '.assets[].name')
n=0
for f in "$DIR"/*; do
  b=$(basename "$f")
  if echo "$have" | grep -qxF "$b"; then continue; fi
  gh release upload pdfs "$f" -R "$REPO" --clobber && n=$((n+1))
done
echo "uploaded $n new files"
