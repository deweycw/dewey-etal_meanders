#!/usr/bin/env bash
#
# Delete .h5 and .out output files from run directories.
#
# Usage:
#   ./clean_runs.sh <run_dir> [run_dir ...]
#   ./clean_runs.sh run_*

set -euo pipefail

if [ $# -eq 0 ]; then
    echo "Usage: $0 <run_dir> [run_dir ...]"
    exit 1
fi

for dir in "$@"; do
    [ -d "$dir" ] || continue

    files=$(find "$dir" -maxdepth 1 \( -name '*.h5' -o -name '*.out' \))
    if [ -z "$files" ]; then
        echo "$dir: no output files"
        continue
    fi

    echo "$files" | xargs rm
    echo "$dir: cleaned"
done
