#!/usr/bin/env bash
# Deletes the Trivy scan categories on a branch that the build matrix no longer
# makes.
#
# An alert closes only when a new upload in its category no longer finds it. A
# category that gets no more uploads keeps its alerts open forever. That
# happens when a Postgres major leaves versions.yaml, or when the category name
# changes. Deleting every analysis in such a category removes the alerts that
# only that category found. GitHub has no setting that does this.
#
# Input:  the build matrix as JSON on stdin, as build_matrix.py prints it.
# Env:    GITHUB_REPOSITORY (owner/name), REF (for example refs/heads/main),
#         and GH_TOKEN with `security-events: write`.
#         DRY_RUN=1 prints the stale categories and deletes nothing.
set -euo pipefail

: "${GITHUB_REPOSITORY:?}" "${REF:?}"

# This name must match the `category` of the upload step in ci.yml.
expected=$(jq -r '.include[]
  | "trivy-\(.variant)-\(.pg_major)-\(if .is_newest_vectorchord then "newest" else .vectorchord end)"' \
  | sort -u)
echo "Categories that the matrix makes:"
echo "$expected" | sed 's/^/  /'

list() {
  gh api --paginate \
    "repos/$GITHUB_REPOSITORY/code-scanning/analyses?ref=$REF&tool_name=Trivy&per_page=100" \
    --jq '.[] | [.category, .id, .deletable] | @tsv'
}

# Each `list` result goes into a variable before any filter runs. A failed API
# call then ends the script through `set -e`, and `|| true` covers only a grep
# that matched nothing.
analyses=$(list)
stale=$(echo "$analyses" | cut -f1 | grep '^trivy-' | sort -u | comm -23 - <(echo "$expected") || true)
if [ -z "$stale" ]; then
  echo "No stale category on $REF."
  exit 0
fi
if [ -n "${DRY_RUN:-}" ]; then
  echo "$stale" | sed 's/^/Would delete /'
  exit 0
fi

# Only the newest analysis of a set is deletable, and one category can hold
# more than one set. Each pass deletes what is deletable and lists again, until
# no analysis of a stale category is left.
while :; do
  analyses=$(list)
  ids=$(echo "$analyses" | awk -F'\t' 'NR == FNR { want[$0] = 1; next }
    ($1 in want) && $3 == "true" { print $2 }' <(echo "$stale") -)
  [ -n "$ids" ] || break
  for id in $ids; do
    gh api --silent --method DELETE \
      "repos/$GITHUB_REPOSITORY/code-scanning/analyses/$id?confirm_delete=true"
    echo "Deleted analysis $id."
  done
done

analyses=$(list)
left=$(echo "$analyses" | cut -f1 | grep -Fx -f <(echo "$stale") || true)
if [ -n "$left" ]; then
  echo "::warning::Analyses that cannot be deleted are left in:"$'\n'"$left"
fi
echo "Deleted the stale categories:"$'\n'"$stale"
