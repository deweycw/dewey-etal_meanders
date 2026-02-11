#!/bin/bash

CALIBRATION_DIR="/home/christiandewey/Code/dewey-etal_meanders/calibration"
PFLOTRAN_EXE="/home/christiandewey/Code/pflotran/src/pflotran/pflotran"

RUN_ID=$1
RUN_DIR="$CALIBRATION_DIR/run_$RUN_ID"

N_TASKS=8

cd "$RUN_DIR" || { echo "ERROR: Cannot cd to $RUN_DIR"; exit 1; }

echo "Start time: $(date)"
echo "=========================================="

# ============================================================
# Step 1: Spin-up
# ============================================================
SPIN_INPUT="pflotran-mcp19_${RUN_ID}_spin.in"
SPIN_CHECKPOINT="pflotran-mcp19_${RUN_ID}_spin-restart.chk"

echo "Running spin-up: $SPIN_INPUT"
mpirun -np $N_TASKS $PFLOTRAN_EXE \
    -pflotranin $RUN_DIR/$SPIN_INPUT
SPIN_EXIT=$?

if [ $SPIN_EXIT -ne 0 ]; then
    echo "ERROR: Spin-up failed with exit code $SPIN_EXIT"
    echo "$RUN_ID SPIN_FAIL $SPIN_EXIT" >> "${SENSITIVITY_DIR}/failed_runs.log"
    exit 1
fi

if [ ! -f "$SPIN_CHECKPOINT" ]; then
    echo "ERROR: Spin-up completed but checkpoint file not found: $SPIN_CHECKPOINT"
    echo "$RUN_ID SPIN_NO_CHECKPOINT" >> "${SENSITIVITY_DIR}/failed_runs.log"
    exit 1
fi

echo "Spin-up complete: $(date)"

# ============================================================
# Step 2: Main simulation
# ============================================================
MAIN_INPUT="pflotran-mcp19_${RUN_ID}.in"

echo "Running main simulation: $MAIN_INPUT"

mpirun -np $N_TASKS $PFLOTRAN_EXE \
    -pflotranin $RUN_DIR/$MAIN_INPUT
MAIN_EXIT=$?

if [ $MAIN_EXIT -ne 0 ]; then
    echo "ERROR: Main simulation failed with exit code $MAIN_EXIT"
    echo "$RUN_ID MAIN_FAIL $MAIN_EXIT" >> "${SENSITIVITY_DIR}/failed_runs.log"
    exit 1
fi

echo "=========================================="
echo "Run $RUN_ID complete: $(date)"
echo "=========================================="
