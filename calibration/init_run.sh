#!/usr/bin/env bash
#
# Create the first calibration run for a meander/year from pflotran_generator.py
# output. Later runs are cloned from it with new_run.sh.
#
# Shared inputs (grid, river-stage files, trans-top-bcs/, hanford-cd.dat) are
# copied once to shared/<cfg>/ and the .in files are rewritten to point
# there, so every run of that configuration uses the same boundary conditions.
#
# Usage:
#   ./init_run.sh <run_id> --meander mcp|mzt --year 2018|2019 [--scenario dam|nodam]
#                 [--chemistry-from <run_dir>] [--from <generator_output_dir>]
#
# <cfg> is <meander><yy>, plus 'nd' for the MZT 2018 no-dam scenario (mzt18nd).
# --scenario applies only to MZT 2018 (default: dam).
#
# Without --from, the generator is run to produce fresh inputs.
#
# --chemistry-from (optional) replaces the CHEMISTRY block (reaction network and
# parameter values) with the one from an existing calibration run, e.g. to start
# from a later calibration than the one in TEMPLATE-chemistry.txt.
#
# Example:
#   ./init_run.sh mzt18_cal000 --meander mzt --year 2018
#   ./init_run.sh mzt18nd_cal000 --meander mzt --year 2018 --scenario nodam

set -euo pipefail

CALIBRATION_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$CALIBRATION_DIR")"
SIM_DIR="$PROJECT_ROOT/pflotran/simulations"
PYTHON="$PROJECT_ROOT/env/bin/python"
[ -x "$PYTHON" ] || PYTHON=python3

usage() {
    echo "Usage: $0 <run_id> --meander mcp|mzt --year 2018|2019 [--scenario dam|nodam] [--chemistry-from <run_dir>] [--from <generator_output_dir>]"
    exit 1
}

RUN_ID=""
MEANDER=""
YEAR=""
SCENARIO=""
FROM=""
CHEM_FROM=""
while [ $# -gt 0 ]; do
    case "$1" in
        --meander) MEANDER="$2"; shift 2 ;;
        --year)    YEAR="$2"; shift 2 ;;
        --scenario) SCENARIO="$2"; shift 2 ;;
        --from)    FROM="$2"; shift 2 ;;
        --chemistry-from) CHEM_FROM="$2"; shift 2 ;;
        -h|--help) usage ;;
        -*)        echo "Unknown option: $1"; usage ;;
        *)         RUN_ID="${1#run_}"; shift ;;
    esac
done

[ -n "$RUN_ID" ] && [ -n "$MEANDER" ] && [ -n "$YEAR" ] || usage
case "$MEANDER" in mcp|mzt) ;; *) echo "Error: --meander must be mcp or mzt"; exit 1 ;; esac
case "$YEAR" in 2018|2019) ;; *) echo "Error: --year must be 2018 or 2019"; exit 1 ;; esac

TAG=""
if [ -n "$SCENARIO" ]; then
    if [ "$MEANDER$YEAR" != "mzt2018" ]; then
        echo "Error: --scenario applies only to --meander mzt --year 2018"; exit 1
    fi
    case "$SCENARIO" in
        dam)   TAG="" ;;
        nodam) TAG="nd" ;;
        *)     echo "Error: --scenario must be dam or nodam"; exit 1 ;;
    esac
fi

CFG="${MEANDER}${YEAR: -2}${TAG}"
RUN_DIR="$CALIBRATION_DIR/run_$RUN_ID"
SHARED_REL="../shared/$CFG"
SHARED_DIR="$CALIBRATION_DIR/shared/$CFG"

if [ -d "$RUN_DIR" ]; then
    echo "Error: '$RUN_DIR' already exists"
    exit 1
fi

if [ -n "$CHEM_FROM" ]; then
    CHEM_FROM="$(cd "$CALIBRATION_DIR" && cd "$CHEM_FROM" && pwd)" || {
        echo "Error: --chemistry-from directory not found"; exit 1; }
    chem_src="$(ls "$CHEM_FROM"/pflotran-*.in 2>/dev/null | grep -v '_spin\.in$' | head -1 || true)"
    [ -f "$chem_src" ] || { echo "Error: no transient .in file in $CHEM_FROM"; exit 1; }
fi

# ------------------------------------------------------------
# 1. Generator output
# ------------------------------------------------------------
if [ -z "$FROM" ]; then
    gen_args=(--year "$YEAR" --meander "$MEANDER")
    [ -n "$SCENARIO" ] && gen_args+=(--scenario "$SCENARIO")
    echo "Running pflotran_generator.py ${gen_args[*]} ..."
    gen_log="$(cd "$SIM_DIR" && "$PYTHON" pflotran_generator.py "${gen_args[@]}")" || {
        echo "$gen_log"; echo "Error: generator failed"; exit 1; }
    FROM="$(echo "$gen_log" | sed -n 's/^ *Directory: *//p' | tail -1)"
fi
FROM="$(cd "$FROM" && pwd)"

src_trans="$(ls "$FROM"/pflotran-"$CFG"_*.in 2>/dev/null | grep -v '_spin\.in$' | head -1 || true)"
src_spin="${src_trans%.in}_spin.in"
if [ ! -f "$src_trans" ] || [ ! -f "$src_spin" ]; then
    echo "Error: no pflotran-${CFG}_*.in / *_spin.in pair found in $FROM"
    exit 1
fi
echo "Source inputs: $FROM"

# ------------------------------------------------------------
# 2. Shared inputs for this configuration (created once)
# ------------------------------------------------------------
grid_name="$(grep -m1 -oE 'xxgrid010-[a-z]+-cxc-top\.h5' "$src_trans")"
hydro_files="$(grep -E '^\s*DATUM FILE ' "$src_trans" | grep -v 'trans-top-bcs' | awk '{print $3}' | xargs -n1 basename | sort -u)"

if [ -d "$SHARED_DIR" ]; then
    echo "Using existing shared inputs: $SHARED_DIR"
else
    echo "Creating shared inputs: $SHARED_DIR"
    mkdir -p "$SHARED_DIR"
    cp "$SIM_DIR/$grid_name" "$SHARED_DIR/"
    cp -r "$FROM/trans-top-bcs" "$SHARED_DIR/"
    cp "$FROM/hanford-cd.dat" "$SHARED_DIR/"
    for f in $hydro_files; do
        cp "$FROM/$f" "$SHARED_DIR/"
    done
fi

# ------------------------------------------------------------
# 3. Run directory with renamed, re-pointed input files
# ------------------------------------------------------------
mkdir "$RUN_DIR"
dst_trans="$RUN_DIR/pflotran-${CFG}_${RUN_ID}.in"
dst_spin="$RUN_DIR/pflotran-${CFG}_${RUN_ID}_spin.in"
cp "$src_trans" "$dst_trans"
cp "$src_spin" "$dst_spin"

# Splice in the CHEMISTRY block (between the CHEMISTRY and CONSTRAINTS section
# headers) from another run. Spin-up and transient share the same block.
if [ -n "$CHEM_FROM" ]; then
    echo "Chemistry from: $chem_src"
    chem_block="$(mktemp)"
    awk '/^[[:space:]]*#===+.*CHEMISTRY/ {inside=1; next}
         /^[[:space:]]*#===+.*CONSTRAINTS/ {inside=0}
         inside' "$chem_src" > "$chem_block"
    [ -s "$chem_block" ] || { echo "Error: no CHEMISTRY block found in $chem_src"; exit 1; }
    for f in "$dst_trans" "$dst_spin"; do
        awk -v blk="$chem_block" '
            /^[[:space:]]*#===+.*CHEMISTRY/ {print; while ((getline l < blk) > 0) print l; skip=1; next}
            /^[[:space:]]*#===+.*CONSTRAINTS/ {skip=0}
            !skip' "$f" > "$f.tmp" && mv "$f.tmp" "$f"
    done
    rm -f "$chem_block"
fi

for f in "$dst_trans" "$dst_spin"; do
    sed -i -E \
        -e "s#^(\s*FILE )\S*(xxgrid010-[a-z]+-cxc-top\.h5)#\1${SHARED_REL}/\2#" \
        -e "s#^(\s*DATUM FILE )\S*trans-top-bcs/#\1${SHARED_REL}/trans-top-bcs/#" \
        -e "/trans-top-bcs/! s#^(\s*DATUM FILE )(\S*/)?([^/[:space:]]+\.txt)#\1${SHARED_REL}/\3#" \
        -e "s#^(\s*DATABASE )\S*hanford-cd\.dat#\1${SHARED_REL}/hanford-cd.dat#" \
        -e "s#^(\s*FILENAME )\S*_spin-restart\.chk#\1pflotran-${CFG}_${RUN_ID}_spin-restart.chk#" \
        "$f"
done

# ------------------------------------------------------------
# 4. Verify every referenced input file resolves from the run directory
# ------------------------------------------------------------
missing=0
while read -r ref; do
    [ -e "$RUN_DIR/$ref" ] || { echo "  MISSING: $ref"; missing=$((missing + 1)); }
done < <(grep -hE '^\s*(DATUM )?FILE |^\s*DATABASE ' "$dst_trans" "$dst_spin" | awk '{print $NF}' | sort -u)

if [ "$missing" -gt 0 ]; then
    echo "Error: $missing referenced file(s) not found -- check $RUN_DIR"
    exit 1
fi

echo "Created $RUN_DIR"
echo "  $(basename "$dst_spin")"
echo "  $(basename "$dst_trans")"
echo "Next: edit parameters, then ./submit.sh $RUN_ID --meander $MEANDER --year $YEAR${SCENARIO:+ --scenario $SCENARIO}"
