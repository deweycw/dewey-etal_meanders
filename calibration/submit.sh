#!/bin/bash
#
# Run spin-up then transient simulation for a calibration run.
#
# Usage:
#   ./submit.sh <run_id> [--meander mcp|mzt] [--year 2018|2019] [--scenario dam|nodam]
#
# Defaults to --meander mcp --year 2019. --scenario applies only to MZT 2018
# (default: dam; nodam runs are named pflotran-mzt18nd_<run_id>).

CALIBRATION_DIR="/home/christiandewey/Code/dewey-etal_meanders/calibration"
PFLOTRAN_EXE="/home/christiandewey/Code/pflotran/src/pflotran/pflotran"

RUN_ID=""
MEANDER="mcp"
YEAR="2019"
SCENARIO=""
while [ $# -gt 0 ]; do
    case "$1" in
        --meander) MEANDER="$2"; shift 2 ;;
        --year)    YEAR="$2"; shift 2 ;;
        --scenario) SCENARIO="$2"; shift 2 ;;
        -*)        echo "Unknown option: $1"; exit 1 ;;
        *)         RUN_ID="${1#run_}"; shift ;;
    esac
done

if [ -z "$RUN_ID" ]; then
    echo "Usage: $0 <run_id> [--meander mcp|mzt] [--year 2018|2019] [--scenario dam|nodam]"
    exit 1
fi
case "$MEANDER" in mcp|mzt) ;; *) echo "ERROR: --meander must be mcp or mzt"; exit 1 ;; esac
case "$YEAR" in 2018|2019) ;; *) echo "ERROR: --year must be 2018 or 2019"; exit 1 ;; esac

TAG=""
if [ -n "$SCENARIO" ]; then
    if [ "$MEANDER$YEAR" != "mzt2018" ]; then
        echo "ERROR: --scenario applies only to --meander mzt --year 2018"; exit 1
    fi
    case "$SCENARIO" in
        dam)   TAG="" ;;
        nodam) TAG="nd" ;;
        *)     echo "ERROR: --scenario must be dam or nodam"; exit 1 ;;
    esac
fi

PREFIX="pflotran-${MEANDER}${YEAR: -2}${TAG}_${RUN_ID}"
RUN_DIR="$CALIBRATION_DIR/run_$RUN_ID"

N_TASKS=8

cd "$RUN_DIR" || { echo "ERROR: Cannot cd to $RUN_DIR"; exit 1; }

echo "Start time: $(date)"
echo "=========================================="

# ============================================================
# Step 1: Spin-up
# ============================================================
SPIN_INPUT="${PREFIX}_spin.in"
SPIN_CHECKPOINT="${PREFIX}_spin-restart.chk"

if [ ! -f "$SPIN_INPUT" ]; then
    echo "ERROR: Spin-up input not found: $RUN_DIR/$SPIN_INPUT"
    exit 1
fi

echo "Running spin-up: $SPIN_INPUT"
mpirun -np $N_TASKS $PFLOTRAN_EXE \
    -pflotranin $RUN_DIR/$SPIN_INPUT
SPIN_EXIT=$?

if [ $SPIN_EXIT -ne 0 ]; then
    echo "ERROR: Spin-up failed with exit code $SPIN_EXIT"
    echo "$RUN_ID SPIN_FAIL $SPIN_EXIT" >> "${RUN_DIR}/failed_runs.log"
    exit 1
fi

if [ ! -f "$SPIN_CHECKPOINT" ]; then
    echo "ERROR: Spin-up completed but checkpoint file not found: $SPIN_CHECKPOINT"
    echo "$RUN_ID SPIN_NO_CHECKPOINT" >> "${RUN_DIR}/failed_runs.log"
    exit 1
fi

echo "Spin-up complete: $(date)"

# ============================================================
# Step 2: Main simulation
# ============================================================
MAIN_INPUT="${PREFIX}.in"

echo "Running main simulation: $MAIN_INPUT"

mpirun -np $N_TASKS $PFLOTRAN_EXE \
    -pflotranin $RUN_DIR/$MAIN_INPUT
MAIN_EXIT=$?

if [ $MAIN_EXIT -ne 0 ]; then
    echo "ERROR: Main simulation failed with exit code $MAIN_EXIT"
    echo "$RUN_ID MAIN_FAIL $MAIN_EXIT" >> "${RUN_DIR}/failed_runs.log"
    exit 1
fi

echo "=========================================="
echo "Run $RUN_ID complete: $(date)"
echo "=========================================="
