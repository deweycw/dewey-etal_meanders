#!/usr/bin/env bash
#
# Create a new run directory by copying input files from an existing one.
# The .in files are renamed to match the new run ID.
#
# Usage:
#   ./new_run.sh <new_run_dir> <source_run_dir>
#
# Example:
#   ./new_run.sh run_manual_cal001 run_default

set -euo pipefail

if [ $# -ne 2 ]; then
    echo "Usage: $0 <new_run_dir> <source_run_dir>"
    exit 1
fi

NEW_DIR="$1"
SRC_DIR="$2"

if [ ! -d "$SRC_DIR" ]; then
    echo "Error: source directory '$SRC_DIR' does not exist"
    exit 1
fi

if [ -d "$NEW_DIR" ]; then
    echo "Error: '$NEW_DIR' already exists"
    exit 1
fi

# Extract run IDs from directory names (strip "run_" prefix)
SRC_ID="${SRC_DIR#run_}"
NEW_ID="${NEW_DIR#run_}"

mkdir "$NEW_DIR"

copied=0
for f in "$SRC_DIR"/*.in; do
    [ -e "$f" ] || continue
    newname="$(basename "$f" | sed "s/${SRC_ID}/${NEW_ID}/g")"
    cp "$f" "$NEW_DIR/$newname"
    echo "  $f -> $NEW_DIR/$newname"
    copied=$((copied + 1))
done

if [ "$copied" -eq 0 ]; then
    echo "Warning: no .in files found in '$SRC_DIR'"
else
    echo "Created $NEW_DIR with $copied input file(s)"
fi
