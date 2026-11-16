#!/usr/bin/env bash
# preflight.sh: safety checks before a commit.
#
# Usage:
#   bash scripts/preflight.sh            # check staged changes (run before every commit)
#   bash scripts/preflight.sh --tree     # check the working tree (tracked + untracked, not ignored)
#   bash scripts/preflight.sh --full     # staged checks, then make lint and make test
#
# Private words to block are read from .preflight-terms (one term or regex per
# line, # for comments). That file is local only and listed in .git/info/exclude.
# Exit code 0 = pass, 1 = fail.

set -uo pipefail

MODE="staged"
FULL=0
for arg in "$@"; do
  case "$arg" in
    --tree) MODE="tree" ;;
    --full) FULL=1 ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "Unknown option: $arg"; exit 2 ;;
  esac
done

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || { echo "FAIL: not inside a git repository"; exit 1; }
cd "$ROOT" || exit 1

FAILS=0
WARNS=0
fail() { echo "FAIL: $*"; FAILS=$((FAILS + 1)); }
warn() { echo "WARN: $*"; WARNS=$((WARNS + 1)); }
ok()   { echo "ok:   $*"; }

# Files that must stay local only.
PRIVATE_FILES='^(BUILD_PROMPT\.md|HANDOFF\.md|COMMIT_PLAN\.md|PROGRESS\.md|CLAUDE\.private\.md|\.preflight-terms|UPDATED_context_section7\.md|git-info-exclude\.txt|TESTING_GUIDE\.md|REPORT\.md|review\.zip)$'

# Blocked file types and paths.
BLOCKED_PATHS='(\.zip|\.tfstate|\.tfstate\.backup|\.tfplan|\.duckdb|\.duckdb\.wal|\.db|\.sqlite|\.parquet|\.pkl|\.joblib|\.h5|\.onnx|\.pt|\.pem|\.key|\.p12|\.tar|\.tar\.gz|\.tgz|\.whl)$|(^|/)\.env$|(^|/)\.terraform/|^data/|^site/data/'

# Secret-looking patterns (extended regex).
SECRET_PATTERNS='AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----|LOCALSTACK_AUTH_TOKEN[[:space:]]*[:=][[:space:]]*["'"'"']?[A-Za-z0-9._-]{8,}|dapi[0-9a-f]{32}|[a-z0-9-]+\.cloud\.databricks\.com|ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|(aws_secret_access_key|aws_access_key_id)[[:space:]]*[:=][[:space:]]*["'"'"']?[A-Za-z0-9/+]{16,}'

MAX_BYTES=1048576        # 1 MB for any file
MAX_MEDIA_BYTES=2097152  # 2 MB for files under docs/media/
MAX_FIXTURE_BYTES=204800 # 200 KB for files under tests/fixtures/

# ---------------------------------------------------------------- file list
if [ "$MODE" = "staged" ]; then
  FILES="$(git diff --cached --name-only --diff-filter=ACMR)"
  echo "preflight: checking staged changes"
  if [ -z "$FILES" ] && [ -z "$(git diff --cached --name-only)" ]; then
    warn "nothing is staged"
  fi
else
  FILES="$(git ls-files --cached --others --exclude-standard)"
  echo "preflight: checking working tree (tracked and untracked, not ignored)"
fi

# ---------------------------------------------------------------- 1. private files
if [ -n "$FILES" ]; then
  HITS="$(printf '%s\n' "$FILES" | grep -E "$PRIVATE_FILES" || true)"
else
  HITS=""
fi
if [ -n "$HITS" ]; then
  fail "local-only files would be committed: $(echo "$HITS" | tr '\n' ' ')"
  echo "      add them to .git/info/exclude and unstage with: git restore --staged <file>"
else
  ok "no local-only files"
fi
TRACKED_PRIVATE="$(git ls-files | grep -E "$PRIVATE_FILES" || true)"
[ -n "$TRACKED_PRIVATE" ] && fail "local-only files are already tracked: $(echo "$TRACKED_PRIVATE" | tr '\n' ' ')"

# ---------------------------------------------------------------- 2. blocked paths
if [ -n "$FILES" ]; then
  HITS="$(printf '%s\n' "$FILES" | grep -E "$BLOCKED_PATHS" || true)"
else
  HITS=""
fi
if [ -n "$HITS" ]; then
  fail "blocked file types or paths: $(echo "$HITS" | tr '\n' ' ')"
else
  ok "no blocked file types (archives, state, data, keys, model weights)"
fi

# ---------------------------------------------------------------- 3. sizes
SIZE_FAIL=0
while IFS= read -r f; do
  [ -z "$f" ] && continue
  [ -f "$f" ] || continue
  sz=$(wc -c < "$f" | tr -d ' ')
  if [[ "$f" == docs/media/* ]]; then
    if [ "$sz" -gt "$MAX_MEDIA_BYTES" ]; then fail "media file over 2 MB: $f ($sz bytes)"; SIZE_FAIL=1; fi
  elif [ "$sz" -gt "$MAX_BYTES" ]; then
    fail "file over 1 MB: $f ($sz bytes)"; SIZE_FAIL=1
  elif [[ "$f" == tests/fixtures/* ]] && [ "$sz" -gt "$MAX_FIXTURE_BYTES" ]; then
    fail "fixture over 200 KB: $f ($sz bytes)"; SIZE_FAIL=1
  fi
done <<< "$FILES"
[ "$SIZE_FAIL" -eq 0 ] && ok "file sizes within limits"

# ---------------------------------------------------------------- 4. private terms
TERMS_FILE=".preflight-terms"
if [ -f "$TERMS_FILE" ]; then
  if ! git check-ignore -q "$TERMS_FILE"; then
    fail "$TERMS_FILE is not ignored; add it to .git/info/exclude"
  fi
  TERMS="$(grep -vE '^[[:space:]]*(#|$)' "$TERMS_FILE" | paste -sd '|' -)"
  if [ -z "$TERMS" ]; then
    warn "$TERMS_FILE has no terms"
  else
    TERM_FAIL=0
    while IFS= read -r f; do
      [ -z "$f" ] && continue
      [ -f "$f" ] || continue
      out="$(grep -InwiE "$TERMS" -- "$f" 2>/dev/null || true)"
      if [ -n "$out" ]; then
        # Print file:line only, never the matched text.
        echo "$out" | cut -d: -f1 | sed "s|^|      $f:|" | head -20
        TERM_FAIL=1
      fi
    done <<< "$FILES"
    if [ "$MODE" = "staged" ]; then
      if git diff --cached -U0 | grep -E '^\+' | grep -v '^+++' | grep -qiwE "$TERMS"; then
        TERM_FAIL=1
        echo "      (match in staged diff lines)"
      fi
    fi
    if [ "$TERM_FAIL" -eq 1 ]; then
      fail "private terms found (locations above; text not printed)"
    else
      ok "no private terms"
    fi
  fi
else
  warn "$TERMS_FILE not found; private-term check skipped (see HANDOFF.md)"
fi

# ---------------------------------------------------------------- 4b. AI log drafts
# Draft entries are expected while Claude Code builds (tree mode: warn).
# They must not be committed: the owner confirms each entry first (staged mode: fail).
if [ -f docs/ai-log.md ] && grep -q "DRAFT: to be confirmed" docs/ai-log.md; then
  if [ "$MODE" = "staged" ] && printf '%s\n' "$FILES" | grep -qx "docs/ai-log.md"; then
    fail "docs/ai-log.md has unconfirmed DRAFT entries; confirm each one, remove the marker, then stage it"
  else
    warn "docs/ai-log.md has DRAFT entries to confirm before it is committed"
  fi
else
  ok "no unconfirmed AI-log drafts"
fi

# ---------------------------------------------------------------- 5. secrets
SEC_FAIL=0
while IFS= read -r f; do
  [ -z "$f" ] && continue
  [ -f "$f" ] || continue
  out="$(grep -InE "$SECRET_PATTERNS" -- "$f" 2>/dev/null || true)"
  if [ -n "$out" ]; then
    echo "$out" | cut -d: -f1 | sed "s|^|      $f:|" | head -20
    SEC_FAIL=1
  fi
done <<< "$FILES"
if [ "$SEC_FAIL" -eq 1 ]; then
  fail "secret-like values found (locations above; values not printed)"
else
  ok "no secret-like values"
fi

# ---------------------------------------------------------------- 6. commit identity
EMAIL="$(git config --get user.email || true)"
if [ -z "$EMAIL" ]; then
  fail "git user.email is not set for this repo"
elif [[ "$EMAIL" != *"+cesinata@users.noreply.github.com" ]]; then
  fail "git user.email is not the cesinata noreply address (check: git config --show-origin --get-all user.email)"
else
  ok "commit identity is the noreply address"
fi

# ---------------------------------------------------------------- 7. optional full run
if [ "$FULL" -eq 1 ]; then
  if [ -f Makefile ]; then
    if make lint && make test; then ok "make lint and make test passed"; else fail "make lint or make test failed"; fi
  else
    warn "no Makefile; lint and tests skipped"
  fi
fi

echo "preflight: $FAILS failure(s), $WARNS warning(s)"
[ "$FAILS" -eq 0 ]
