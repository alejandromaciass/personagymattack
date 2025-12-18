#!/usr/bin/env bash
set -euo pipefail

# Runs a minimal, reproducible PersonaGym-R demo for recording.
# Produces 3 runs with the same task+seed using different white agents:
# - prompt (baseline)
# - tool   (baseline)
# - bad    (intentionally breaks persona)

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON:-$ROOT_DIR/.venv/bin/python}"
TASK="${TASK:-$ROOT_DIR/tasks/travel_yosemite_001}"
SEED="${SEED:-7}"

run_one () {
  local white="$1"
  echo
  echo "=============================="
  echo "Running white=${white} task=$(basename "$TASK") seed=$SEED"
  echo "=============================="
  "$PY" -m src.personagym_r.run_green --task "$TASK" --white "$white" --seed "$SEED"
}

latest_report_dir () {
  ls -1dt "$ROOT_DIR"/reports/* 2>/dev/null | head -n 1
}

score_line () {
  local report_dir="$1"
  # Pull the markdown table row for R (overall) if present.
  grep -E '^\| R \|' "$report_dir/summary.md" || true
}

run_one prompt
PROMPT_DIR="$(latest_report_dir)"

run_one tool
TOOL_DIR="$(latest_report_dir)"

run_one bad
BAD_DIR="$(latest_report_dir)"

echo
echo "=== Report directories ==="
echo "prompt: $PROMPT_DIR"
echo "tool:   $TOOL_DIR"
echo "bad:    $BAD_DIR"

echo
echo "=== Overall score (R) lines ==="
echo "prompt: $(score_line "$PROMPT_DIR")"
echo "tool:   $(score_line "$TOOL_DIR")"
echo "bad:    $(score_line "$BAD_DIR")"

echo
echo "Tip: open each summary in the editor:"
echo "  $PROMPT_DIR/summary.md"
echo "  $TOOL_DIR/summary.md"
echo "  $BAD_DIR/summary.md"
