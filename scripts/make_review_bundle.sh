#!/usr/bin/env bash
# make_review_bundle.sh: write review.zip for upload to a review chat.
#
# Includes: every tracked or untracked file that git does not ignore, plus the
# local reports REPORT.md, PROGRESS.md and COMMIT_PLAN.md if they exist.
# Leaves out: .git, data, virtual environments, .env files, build prompts,
# .preflight-terms and any file over 1 MB. Prints what it skipped.
#
# Usage: bash scripts/make_review_bundle.sh [output.zip]
# Exit code 0 = zip written, 1 = failed.

set -uo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || { echo "FAIL: not inside a git repository"; exit 1; }
cd "$ROOT" || exit 1
command -v zip >/dev/null 2>&1 || { echo "FAIL: zip is not installed"; exit 1; }

OUT="${1:-review.zip}"
MAX_BYTES=1048576
SKIP_RE='^(\.git/|\.venv/|venv/|data/|site/data/|node_modules/|\.terraform/|BUILD_PROMPT\.md$|HANDOFF\.md$|TESTING_GUIDE\.md$|\.preflight-terms$|git-info-exclude\.txt$|review\.zip$)|(^|/)\.env(\..*)?$|(^|/)__pycache__/|\.(tfstate|tfstate\.backup|duckdb|zip|pem|key)$'

LIST="$(mktemp)"
trap 'rm -f "$LIST"' EXIT

{
  git ls-files --cached --others --exclude-standard
  for f in REPORT.md PROGRESS.md COMMIT_PLAN.md; do [ -f "$f" ] && echo "$f"; done
} | sort -u > "$LIST"

KEEP="$(mktemp)"
trap 'rm -f "$LIST" "$KEEP"' EXIT
SKIPPED=0
while IFS= read -r f; do
  [ -z "$f" ] && continue
  [ -f "$f" ] || continue                       # tracked but deleted in the working tree
  if printf '%s\n' "$f" | grep -qE "$SKIP_RE"; then
    echo "skip (excluded type or path): $f"; SKIPPED=$((SKIPPED + 1)); continue
  fi
  sz=$(wc -c < "$f" | tr -d ' ')
  if [ "$sz" -gt "$MAX_BYTES" ]; then
    echo "skip (over 1 MB): $f ($sz bytes)"; SKIPPED=$((SKIPPED + 1)); continue
  fi
  echo "$f" >> "$KEEP"
done < "$LIST"

[ -s "$KEEP" ] || { echo "FAIL: nothing to zip"; exit 1; }

rm -f "$OUT"
if ! zip -qX "$OUT" -@ < "$KEEP"; then echo "FAIL: zip failed"; exit 1; fi

echo "wrote $OUT: $(wc -l < "$KEEP" | tr -d ' ') files, $(wc -c < "$OUT" | tr -d ' ') bytes, $SKIPPED skipped"
[ -f REPORT.md ] || echo "WARN: REPORT.md not found; the review will be weaker without it"
if git check-ignore -q "$OUT" 2>/dev/null; then :; else echo "WARN: $OUT is not git-ignored; add it to .git/info/exclude"; fi
exit 0
