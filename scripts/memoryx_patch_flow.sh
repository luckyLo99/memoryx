#!/usr/bin/env bash
# scripts/memoryx_patch_flow.sh
#
# MemoryX clean patch/hotfix workflow.
#
# This script is intentionally strict:
# - never moves existing tags
# - never tags dirty worktree
# - never uses git add .
# - always gates before tag/release
# - always does archive hygiene before release
#
# Usage:
#   ./scripts/memoryx_patch_flow.sh start hotfix/v2.0.1-issue-001
#   ./scripts/memoryx_patch_flow.sh status
#   ./scripts/memoryx_patch_flow.sh gate
#   ./scripts/memoryx_patch_flow.sh archive-check
#   ./scripts/memoryx_patch_flow.sh commit "fix: ..."
#   ./scripts/memoryx_patch_flow.sh push
#   ./scripts/memoryx_patch_flow.sh tag v2.0.1
#   ./scripts/memoryx_patch_flow.sh release v2.0.1
#
# Environment:
#   BASE_BRANCH=memoryx-2-kernel
#   GITHUB_REPO=luckyl214/memoryx
#   PYTHON_BIN=python3.12

set -Eeuo pipefail

BASE_BRANCH="${BASE_BRANCH:-memoryx-2-kernel}"
GITHUB_REPO="${GITHUB_REPO:-luckyl214/memoryx}"
PYTHON_BIN="${PYTHON_BIN:-python3.12}"

SCRIPT_NAME="$(basename "$0")"

log() {
  printf '\n[%s] %s\n' "$SCRIPT_NAME" "$*"
}

die() {
  printf '\n[%s] ERROR: %s\n' "$SCRIPT_NAME" "$*" >&2
  exit 1
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

root() {
  git rev-parse --show-toplevel 2>/dev/null || die "Not inside a git repository."
}

cd_root() {
  cd "$(root)"
}

current_branch() {
  git branch --show-current
}

status_short() {
  git status --short
}

assert_clean() {
  if [[ -n "$(status_short)" ]]; then
    git status --short
    die "Worktree is dirty."
  fi
}

assert_dirty_only_allowed_for_commit() {
  if [[ -z "$(status_short)" ]]; then
    die "No changes to commit."
  fi
}

assert_no_protected_tag_change() {
  local protected=("v2.0.0" "v2.0.0-rc.1" "v2.0.0-rc.2")
  for tag in "${protected[@]}"; do
    if git tag -l "$tag" | grep -qx "$tag"; then
      local typ
      typ="$(git cat-file -t "$tag" || true)"
      [[ "$typ" == "tag" ]] || die "Protected tag is not annotated locally: $tag"
    fi
  done
}

assert_not_on_tag() {
  if git describe --exact-match --tags HEAD >/dev/null 2>&1; then
    local t
    t="$(git describe --exact-match --tags HEAD)"
    log "HEAD is exactly at tag $t; this is okay for inspection but not for development."
  fi
}

assert_branch_safe_for_dev() {
  local b
  b="$(current_branch)"
  case "$b" in
    hotfix/*|fix/*|patch/*|docs/*|hygiene/*|feature/*)
      ;;
    *)
      die "Current branch '$b' is not a dev branch. Use hotfix/*, fix/*, patch/*, docs/*, hygiene/*, or feature/*."
      ;;
  esac
}

scan_for_forbidden_files() {
  log "Checking tracked forbidden files"

  local bad=""
  bad="$(git ls-files | grep -E '(^|/)(\.env|reports|artifacts|logs|traces|lancedb|\.sqlite|\.db|__pycache__|\.pytest_cache)(/|$)' || true)"

  if [[ -n "$bad" ]]; then
    printf '%s\n' "$bad"
    die "Forbidden runtime/private files are tracked."
  fi

  log "Tracked forbidden file scan: PASS"
}

scan_for_secrets() {
  log "Scanning for obvious secrets/private paths"

  local tmp
  tmp="$(mktemp)"

  git ls-files \
    | grep -Ev '\.(png|jpg|jpeg|gif|webp|pdf|gz|zip)$' \
    | while read -r f; do
        [[ -f "$f" ]] || continue
        grep -InE '(/home/lucky|/Users/|C:\\|OPENAI_API_KEY|SILICONFLOW_API_KEY|api[_-]?key\s*=|secret\s*=|token\s*=|password\s*=)' "$f" || true
      done > "$tmp"

  # Allow documented placeholders.
  local filtered
  filtered="$(grep -Ev '(your_|placeholder|example|\.env\.example|AGENT_RULES|memoryx_patch_flow|memoryx_repo_guard)' "$tmp" || true)"

  rm -f "$tmp"

  if [[ -n "$filtered" ]]; then
    printf '%s\n' "$filtered"
    die "Possible secret/private path hits found."
  fi

  log "Secret/private path scan: PASS"
}

version_smoke() {
  log "Version smoke"

  python - <<'PY'
import memoryx
v = getattr(memoryx, "__version__", None)
print("memoryx.__version__ =", v)
assert v is not None
PY
}

collect_tests() {
  log "pytest collect-only"
  python -m pytest --collect-only -q
}

run_tests() {
  log "pytest full"
  python -m pytest -q
}

release_gate() {
  log "ReleaseGate"
  python scripts/run_memoryx_release_gate.py
}

optional_lancedb_gate() {
  log "Optional LanceDB gate"

  if python - <<'PY'
import importlib.util
raise SystemExit(0 if importlib.util.find_spec("lancedb") else 1)
PY
  then
    python -m pytest tests/test_lancedb_vector_store.py -q
  else
    log "lancedb not installed; skipping optional LanceDB gate. Use: pip install -e '.[dev,lancedb]'"
  fi
}

archive_check() {
  assert_clean
  scan_for_forbidden_files
  scan_for_secrets

  local outdir="/tmp/memoryx-archive-check-$(date +%Y%m%d-%H%M%S)"
  mkdir -p "$outdir"

  local archive="$outdir/memoryx-check.tar.gz"

  log "Building archive: $archive"
  git archive --format=tar.gz --output="$archive" HEAD

  log "Checking archive file list"
  if tar -tzf "$archive" | grep -E '(^|/)(\.env|reports|artifacts|logs|traces|lancedb|\.sqlite|\.db|__pycache__|\.pytest_cache)(/|$)'; then
    die "Archive contains forbidden runtime/private paths."
  fi

  mkdir -p "$outdir/src"
  tar -xzf "$archive" -C "$outdir/src"

  log "Checking archive content for private paths/secrets"
  local hits
  hits="$(grep -RInE '(/home/lucky|/Users/|C:\\|OPENAI_API_KEY|SILICONFLOW_API_KEY|api[_-]?key\s*=|secret\s*=|token\s*=|password\s*=)' "$outdir/src" || true)"
  hits="$(printf '%s\n' "$hits" | grep -Ev '(your_|placeholder|example|\.env\.example)' || true)"

  if [[ -n "$hits" ]]; then
    printf '%s\n' "$hits"
    die "Archive contains possible secret/private path hits."
  fi

  log "Archive hygiene: PASS"
}

fresh_archive_smoke() {
  assert_clean

  local outdir="/tmp/memoryx-fresh-archive-smoke-$(date +%Y%m%d-%H%M%S)"
  mkdir -p "$outdir/src"

  local archive="$outdir/memoryx-smoke.tar.gz"

  log "Building archive for fresh smoke: $archive"
  git archive --format=tar.gz --output="$archive" HEAD

  tar -xzf "$archive" -C "$outdir/src"

  cd "$outdir/src"

  log "Creating fresh venv"
  "$PYTHON_BIN" -m venv .venv
  # shellcheck disable=SC1091
  . .venv/bin/activate

  python -m pip install --upgrade pip -q
  python -m pip install -e ".[dev]" -q

  python - <<'PY'
import memoryx
print("archive memoryx.__version__ =", getattr(memoryx, "__version__", None))
assert getattr(memoryx, "__version__", None) is not None
PY

  python -m pytest --collect-only -q
  python -m pytest -q

  log "Fresh archive smoke: PASS"
}

cmd_start() {
  local branch="${1:-}"
  [[ -n "$branch" ]] || die "Usage: $SCRIPT_NAME start <branch-name>"

  cd_root
  assert_clean

  log "Updating base branch: $BASE_BRANCH"
  git checkout "$BASE_BRANCH"
  git pull --ff-only origin "$BASE_BRANCH"

  log "Creating branch: $branch"
  git checkout -b "$branch"

  cat <<EOF

Started branch: $branch

Next:
1. Reproduce the bug.
2. Make minimal changes.
3. Run:
   ./scripts/memoryx_patch_flow.sh gate
   ./scripts/memoryx_patch_flow.sh archive-check
4. Commit explicitly.
EOF
}

cmd_status() {
  cd_root
  log "Repository status"
  git status --short
  git branch --show-current
  git log --oneline -5
  git tag -l 'v2.0.0*'
  assert_no_protected_tag_change
}

cmd_gate() {
  cd_root
  assert_branch_safe_for_dev
  assert_no_protected_tag_change
  scan_for_forbidden_files
  scan_for_secrets
  version_smoke
  collect_tests
  run_tests
  release_gate
  optional_lancedb_gate
  log "Gate: PASS"
}

cmd_archive_check() {
  cd_root
  archive_check
  fresh_archive_smoke
  log "Archive check: PASS"
}

cmd_commit() {
  local msg="${1:-}"
  [[ -n "$msg" ]] || die "Usage: $SCRIPT_NAME commit \"message\""

  cd_root
  assert_branch_safe_for_dev
  assert_dirty_only_allowed_for_commit

  cat <<EOF

Files changed:
$(git status --short)

This script refuses to run git add .
You must stage files manually in another shell if needed, or continue here with explicit staging.

Suggested:
  git add <file1> <file2>
  ./scripts/memoryx_patch_flow.sh commit "$msg"

EOF

  local staged
  staged="$(git diff --cached --name-only)"
  if [[ -z "$staged" ]]; then
    die "No staged files. Stage explicit files first. Do not use git add ."
  fi

  log "Staged files:"
  printf '%s\n' "$staged"

  scan_for_forbidden_files
  scan_for_secrets

  log "Committing"
  git commit -m "$msg"
}

cmd_push() {
  cd_root
  assert_branch_safe_for_dev
  local b
  b="$(current_branch)"

  log "Pushing branch: $b"
  git push -u origin "$b"

  cat <<EOF

Now create a GitHub PR.

PR body must include:
- Problem
- Root cause
- Fix
- Files changed
- Tests
- ReleaseGate
- Archive hygiene
- Risk
- Rollback

Do not merge without green checks.
EOF
}

cmd_tag() {
  local tag="${1:-}"
  [[ -n "$tag" ]] || die "Usage: $SCRIPT_NAME tag v2.0.1"

  cd_root
  assert_clean
  assert_no_protected_tag_change

  case "$tag" in
    v2.0.0|v2.0.0-rc.1|v2.0.0-rc.2)
      die "Protected historical tag cannot be created/modified by this script: $tag"
      ;;
    v2.0.*|v2.1.0-rc.*|v2.1.*)
      ;;
    *)
      die "Unexpected tag format: $tag. Expected v2.0.x patch or v2.1.x release line."
      ;;
  esac

  if git tag -l "$tag" | grep -qx "$tag"; then
    die "Tag already exists locally: $tag"
  fi

  if git ls-remote --tags origin "$tag" | grep -q "$tag"; then
    die "Tag already exists remotely: $tag"
  fi

  cmd_gate
  cmd_archive_check

  local commit
  commit="$(git rev-parse --short HEAD)"

  log "Creating annotated tag: $tag -> $commit"
  git tag -a "$tag" -m "MemoryX $tag

Patch release candidate created from clean gated commit.

Validation:
- pytest collect-only: PASS
- pytest full: PASS
- ReleaseGate: PASS
- archive hygiene: PASS
- fresh archive smoke: PASS

Commit: $commit
"

  local typ
  typ="$(git cat-file -t "$tag")"
  [[ "$typ" == "tag" ]] || die "Tag is not annotated: $tag"

  log "Pushing tag: $tag"
  git push origin "$tag"

  log "Tag pushed: $tag"
}

cmd_release() {
  local tag="${1:-}"
  [[ -n "$tag" ]] || die "Usage: $SCRIPT_NAME release v2.0.1"

  cd_root
  assert_clean

  if ! git tag -l "$tag" | grep -qx "$tag"; then
    die "Local tag does not exist: $tag"
  fi

  if ! git ls-remote --tags origin "$tag" | grep -q "$tag"; then
    die "Remote tag does not exist: $tag"
  fi

  local dist="dist"
  mkdir -p "$dist"

  local archive="$dist/memoryx-$tag.tar.gz"
  local checksum="$dist/memoryx-$tag.tar.gz.sha256"
  local notes="RELEASE_NOTES_$tag.md"

  log "Building release archive"
  git archive --format=tar.gz --output="$archive" "$tag"
  shasum -a 256 "$archive" > "$checksum"

  log "Writing release notes: $notes"
  cat > "$notes" <<EOF
# MemoryX $tag

MemoryX $tag patch release.

## Status

- Tag: $tag
- Type: patch
- Prerelease: false
- Base line: MemoryX 2.0.x

## Validation

- pytest collect-only: PASS
- pytest full: PASS
- ReleaseGate: PASS
- archive hygiene: PASS
- fresh archive smoke: PASS

## Notes

Describe the fixed bug or patch scope here before publishing.
EOF

  log "Creating GitHub release draft"
  gh release create "$tag" \
    "$archive" \
    "$checksum" \
    --repo "$GITHUB_REPO" \
    --title "MemoryX $tag" \
    --notes-file "$notes" \
    --verify-tag \
    --draft

  cat <<EOF

Draft release created for $tag.

Before publishing:
1. Open GitHub release draft.
2. Edit notes with exact root cause and fix.
3. Confirm prerelease=false unless this is an rc tag.
4. Publish.
5. Download and verify checksum:

   mkdir -p /tmp/memoryx-$tag-download-check
   gh release download "$tag" --repo "$GITHUB_REPO" --pattern 'memoryx-$tag.tar.gz*' --dir /tmp/memoryx-$tag-download-check
   cd /tmp/memoryx-$tag-download-check
   shasum -a 256 -c memoryx-$tag.tar.gz.sha256
EOF
}

usage() {
  cat <<EOF
Usage:
  $SCRIPT_NAME start <branch>
  $SCRIPT_NAME status
  $SCRIPT_NAME gate
  $SCRIPT_NAME archive-check
  $SCRIPT_NAME commit "message"
  $SCRIPT_NAME push
  $SCRIPT_NAME tag <v2.0.x>
  $SCRIPT_NAME release <v2.0.x>

Examples:
  $SCRIPT_NAME start hotfix/v2.0.1-issue-001
  $SCRIPT_NAME gate
  $SCRIPT_NAME archive-check
  git add explicit_file.py tests/test_explicit.py
  $SCRIPT_NAME commit "fix: repair explicit issue"
  $SCRIPT_NAME push
  $SCRIPT_NAME tag v2.0.1
  $SCRIPT_NAME release v2.0.1
EOF
}

main() {
  need_cmd git

  local cmd="${1:-}"
  shift || true

  case "$cmd" in
    start)
      cmd_start "$@"
      ;;
    status)
      cmd_status
      ;;
    gate)
      cmd_gate
      ;;
    archive-check)
      cmd_archive_check
      ;;
    commit)
      cmd_commit "$@"
      ;;
    push)
      cmd_push
      ;;
    tag)
      cmd_tag "$@"
      ;;
    release)
      need_cmd gh
      cmd_release "$@"
      ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main "$@"
