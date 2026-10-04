#!/usr/bin/env bash
# Release version-bump state machine: resolve the target version, commit the
# bumped files on a bot branch, gate the bump PR on dispatched lint/CI runs,
# then merge it — or close it again on a dry run.
set -euo pipefail

RETRY_ATTEMPTS=${RELEASE_BUMP_RETRY_ATTEMPTS:-5}
RETRY_DELAY_SECONDS=${RELEASE_BUMP_RETRY_DELAY_SECONDS:-10}
RUN_DISCOVER_ATTEMPTS=${RELEASE_BUMP_RUN_DISCOVER_ATTEMPTS:-30}
RUN_DISCOVER_SECONDS=${RELEASE_BUMP_RUN_DISCOVER_SECONDS:-10}
MERGE_WAIT_ATTEMPTS=${RELEASE_BUMP_MERGE_WAIT_ATTEMPTS:-40}
MERGE_WAIT_SECONDS=${RELEASE_BUMP_MERGE_WAIT_SECONDS:-15}
GATE_WORKFLOWS=${RELEASE_BUMP_GATE_WORKFLOWS:-"ci.yml workflow-lint.yml"}
APPROVE_POLLS=${RELEASE_BUMP_APPROVE_POLLS:-10}
APPROVE_IDLE_SECONDS=${RELEASE_BUMP_APPROVE_IDLE_SECONDS:-30}
APPROVE_SEEN_SECONDS=${RELEASE_BUMP_APPROVE_SEEN_SECONDS:-10}

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cd "${GITHUB_WORKSPACE:-$PWD}"

retry() {
  local attempt
  for ((attempt = 1; attempt <= RETRY_ATTEMPTS; attempt++)); do
    if "$@"; then
      return 0
    fi
    if [ "$attempt" -lt "$RETRY_ATTEMPTS" ]; then
      sleep $((attempt * RETRY_DELAY_SECONDS))
    fi
  done
  return 1
}

write_summary() {
  printf '%s\n' "$1"
  if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
    printf '%s\n' "$1" >> "$GITHUB_STEP_SUMMARY"
  fi
}

write_output() {
  printf '%s\n' "$1" >> "$GITHUB_OUTPUT"
}

approve_gated_runs() {
  # Pull_request runs on the bot branch queue as approval-gated
  # action_required runs; poll and approve as in sibling release
  # workflows. Approving them is what satisfies the PR's required checks —
  # the workflow_dispatch runs gated below only verify the branch and
  # never count toward them. A rejected approval is non-fatal.
  local branch=$1
  local gated_seen=0 empty_streak=0 attempt batch gated
  for ((attempt = 1; attempt <= APPROVE_POLLS; attempt++)); do
    batch=$(retry gh run list --repo "$GITHUB_REPOSITORY" --branch "$branch" \
      --event pull_request --status action_required --json databaseId --jq '.[].databaseId' || true)
    if [ -z "$batch" ]; then
      empty_streak=$((empty_streak + 1))
      if { [ "$gated_seen" -eq 0 ] && [ "$empty_streak" -ge 3 ]; } ||
        { [ "$gated_seen" -eq 1 ] && [ "$empty_streak" -ge 2 ]; }; then
        break
      fi
      sleep "$APPROVE_IDLE_SECONDS"
      continue
    fi
    empty_streak=0
    gated_seen=1
    for gated in $batch; do
      retry gh api -X POST "repos/$GITHUB_REPOSITORY/actions/runs/$gated/approve" || true
    done
    sleep "$APPROVE_SEEN_SECONDS"
  done
}

gate_bump_pr() {
  local branch=$1
  local workflow run_id attempt conclusion failed
  local -a workflows=()
  read -r -a workflows <<< "$GATE_WORKFLOWS"
  local started
  started=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  for workflow in "${workflows[@]}"; do
    retry gh workflow run "$workflow" --repo "$GITHUB_REPOSITORY" --ref "$branch"
  done
  failed=0
  for workflow in "${workflows[@]}"; do
    run_id=""
    for ((attempt = 1; attempt <= RUN_DISCOVER_ATTEMPTS; attempt++)); do
      sleep "$RUN_DISCOVER_SECONDS"
      run_id=$(retry gh run list --repo "$GITHUB_REPOSITORY" --workflow "$workflow" \
        --branch "$branch" --event workflow_dispatch --created ">=$started" \
        --json databaseId --jq '.[0].databaseId // empty' || true)
      [ -n "$run_id" ] && break
    done
    if [ -z "$run_id" ]; then
      echo "$workflow dispatch for $branch was not observed; the version PR remains open." >&2
      exit 1
    fi
    gh run watch --repo "$GITHUB_REPOSITORY" "$run_id" --interval 30 || true
    conclusion=$(retry gh run view --repo "$GITHUB_REPOSITORY" "$run_id" \
      --json conclusion --jq '.conclusion // empty' || true)
    if [ "$conclusion" != success ]; then
      echo "$workflow concluded '$conclusion'; the version PR remains open." >&2
      failed=1
    fi
  done
  if [ "$failed" -ne 0 ]; then
    exit 1
  fi
}

CURRENT=$(python3 -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])')
if [ -n "${SET_VERSION:-}" ]; then
  VERSION=${SET_VERSION#v}
  if [ "$VERSION" != "$CURRENT" ]; then
    python3 "$SCRIPT_DIR/bump_version.py" --root "$PWD" --set "$VERSION" >/dev/null
  fi
else
  VERSION=$(python3 "$SCRIPT_DIR/bump_version.py" --root "$PWD" --bump "${BUMP:-patch}")
fi
if git ls-remote --exit-code --tags origin "refs/tags/v${VERSION}"; then
  echo "::error::tag v${VERSION} already exists" >&2
  exit 1
fi
if [ "$VERSION" = "$CURRENT" ]; then
  write_output "version=${VERSION}"
  write_output "sha=$(git rev-parse HEAD)"
  exit 0
fi

branch="bot/release-bump-v${VERSION}-${GITHUB_RUN_ID}"
# Capture the dispatch sha before switching: the dry-run path emits this so
# downstream jobs verify the reachable main commit, not the soon-deleted bot
# branch tip (a full clone of main can never resolve that sha).
DISPATCH_SHA=$(git rev-parse HEAD)
git switch -q -c "$branch"
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git add plugins/dashboard/.plugin/plugin.json pyproject.toml \
  plugins/dashboard/skills/*/SKILL.md uv.lock
git commit -m "Release v${VERSION}: update version files"
retry git push origin "HEAD:refs/heads/${branch}"
body=$(printf '%s\n\n- version: v%s\n- workflow run: %s\n' \
  "Automated dashboard-agent version bump." "$VERSION" \
  "${GITHUB_SERVER_URL}/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}")
pr_url=$(retry gh pr create --repo "$GITHUB_REPOSITORY" --base main --head "$branch" \
  --title "Release v${VERSION}: update version files" --body "$body")

approve_gated_runs "$branch"

gate_bump_pr "$branch"

if [ "${DRY_RUN:-false}" = "true" ]; then
  retry gh pr close --repo "$GITHUB_REPOSITORY" --delete-branch "$pr_url" \
    --comment "Dry run: closing without merge."
  write_output "version=${VERSION}"
  write_output "sha=${DISPATCH_SHA}"
  write_summary "dry run complete: version files verified on $branch"
  exit 0
fi

retry gh pr merge --repo "$GITHUB_REPOSITORY" --auto --squash --delete-branch "$pr_url"
merged=false
for ((attempt = 1; attempt <= MERGE_WAIT_ATTEMPTS; attempt++)); do
  merged_at=$(retry gh api "repos/$GITHUB_REPOSITORY/pulls/${pr_url##*/}" \
    --jq '.merged_at // empty' || true)
  [ -n "$merged_at" ] && { merged=true; break; }
  sleep "$MERGE_WAIT_SECONDS"
done
if [ "$merged" != true ]; then
  echo "version-bump PR did not merge; release was not created." >&2
  exit 1
fi
git fetch -q origin main
write_output "version=${VERSION}"
write_output "sha=$(git rev-parse origin/main)"
