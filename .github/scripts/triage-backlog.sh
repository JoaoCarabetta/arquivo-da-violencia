#!/usr/bin/env bash
# Triage open backlog issues: categorize, label, and move to Todo.
# Used by the hourly Cursor automation "arquivo-da-violencia-backlog-workflow".
set -euo pipefail

REPO="${GITHUB_REPOSITORY:-JoaoCarabetta/arquivo-da-violencia}"

ensure_label() {
  local name="$1" color="$2" description="$3"
  if ! gh label list --repo "$REPO" --json name --jq ".[] | select(.name == \"$name\") | .name" | grep -qx "$name"; then
    gh label create "$name" --repo "$REPO" --color "$color" --description "$description"
    echo "Created label: $name"
  fi
}

ensure_label "status/backlog" "ededed" "Queued; not yet ready for work"
ensure_label "status/todo" "0e8a16" "Categorized and ready to pick up"
ensure_label "status/in-progress" "fbca04" "Actively being worked on"
ensure_label "status/done" "1d76db" "Completed"
ensure_label "area/pipeline" "5319e7" "Ingestion, download, extraction, dedup, enrichment"
ensure_label "area/frontend" "1d76db" "Public portal and admin UI"
ensure_label "area/backend" "006b75" "API, models, and services"
ensure_label "area/geocoding" "e99695" "Maps, coordinates, and location precision"
ensure_label "area/infra" "bfd4f2" "Deploy, CI/CD, and dev environment"

categorize_issue() {
  local title="$1"
  local lower
  lower="$(echo "$title" | tr '[:upper:]' '[:lower:]')"

  local type="enhancement"
  local areas=()

  if [[ "$lower" == *bug* ]] || [[ "$lower" == *fix* ]] || [[ "$lower" == *broken* ]] || [[ "$lower" == *not showing* ]]; then
    type="bug"
  elif [[ "$lower" == *doc* ]]; then
    type="documentation"
  fi

  if [[ "$lower" == *download* ]] || [[ "$lower" == *bot* ]] || [[ "$lower" == *ingest* ]] || [[ "$lower" == *pipeline* ]] || [[ "$lower" == *classif* ]] || [[ "$lower" == *extract* ]] || [[ "$lower" == *fetch* ]]; then
    areas+=("area/pipeline")
  fi
  if [[ "$lower" == *geoloc* ]] || [[ "$lower" == *geocod* ]] || [[ "$lower" == *maps* ]] || [[ "$lower" == *coord* ]]; then
    areas+=("area/geocoding")
  fi
  if [[ "$lower" == *ui* ]] || [[ "$lower" == *sidebar* ]] || [[ "$lower" == *table* ]] || [[ "$lower" == *portal* ]] || [[ "$lower" == *frontend* ]]; then
    areas+=("area/frontend")
  fi
  if [[ "$lower" == *docker* ]] || [[ "$lower" == *deploy* ]] || [[ "$lower" == *ci* ]] || [[ "$lower" == *infra* ]]; then
    areas+=("area/infra")
  fi

  if ((${#areas[@]} == 0)); then
    areas+=("area/backend")
  fi

  echo "$type"
  printf '%s\n' "${areas[@]}"
}

move_to_todo() {
  local number="$1"
  local title="$2"

  mapfile -t categorization < <(categorize_issue "$title")
  local issue_type="${categorization[0]}"
  local -a areas=("${categorization[@]:1}")

  local labels=("$issue_type" "status/todo")
  labels+=("${areas[@]}")

  # Remove backlog status if present; set todo + category labels.
  gh issue edit "$number" --repo "$REPO" \
    --remove-label "status/backlog" \
    --add-label "$(IFS=,; echo "${labels[*]}")"

  local area_list
  area_list="$(printf '`%s` ' "${areas[@]}")"

  gh issue comment "$number" --repo "$REPO" --body "$(cat <<EOF
**Backlog triage** (automated)

| Field | Value |
|-------|-------|
| **Type** | \`$issue_type\` |
| **Area** | ${area_list} |
| **Status** | \`status/todo\` |

Moved from Backlog → **Todo**. Ready to be picked up for implementation.
EOF
)"
  echo "Triaged #$number: type=$issue_type areas=${areas[*]}"
}

echo "=== Triage backlog for $REPO ==="

# Open issues without status/todo or status/in-progress or status/done are backlog candidates.
while IFS=$'\t' read -r number title labels; do
  if [[ "$labels" == *"status/todo"* ]] || [[ "$labels" == *"status/in-progress"* ]] || [[ "$labels" == *"status/done"* ]]; then
    echo "Skipping #$number (already past backlog)"
    continue
  fi
  move_to_todo "$number" "$title"
done < <(
  gh issue list --repo "$REPO" --state open --limit 100 \
    --json number,title,labels \
    --jq '.[] | [.number, .title, ([.labels[].name] | join(","))] | @tsv'
)

echo "=== Done ==="
