#!/bin/bash
#SBATCH --job-name=spin_test
#SBATCH --ntasks=8
#SBATCH --partition=standard
#SBATCH --time=01:00:00
#SBATCH --output=logs/default.out
#SBATCH --error=logs/default.err
#SBATCH --mail-type=ALL
#SBATCH --mail-user=cdewey@udel.edu

# --ntasks=8       : 8 MPI ranks per simulation
# --time           : 180 min wall time per task (spin + main + margin)


# ============================================================
# Load modules
# ============================================================
vpkg_require openmpi
vpkg_require singularity 

# ============================================================
# Paths
# ============================================================
SENSITIVITY_DIR="/lustre/dewey/users/4315/sensitivity"
PFLOTRAN_SIF="/lustre/dewey/sw/pflotran.sif"   
PFLOTRAN_EXE="/pflotran/src/pflotran/pflotran"

# ============================================================
# Construct run directory from task ID
# ============================================================
RUN_ID="000"
RUN_DIR="${SENSITIVITY_DIR}/run${RUN_ID}"

cd "$RUN_DIR" || { echo "ERROR: Cannot cd to $RUN_DIR"; exit 1; }

echo "=========================================="
echo "Run ID:    $RUN_ID"
echo "Start time: $(date)"
echo "=========================================="

# ============================================================
# Step 1: Spin-up
# ============================================================
SPIN_INPUT="pflotran-mcp19_run${RUN_ID}_spin.in"
SPIN_CHECKPOINT="pflotran-mcp19_run${RUN_ID}_spin-restart.chk"

echo "Running spin-up: $SPIN_INPUT"
mpirun -np 4 singularity exec \
    --bind ${SENSITIVITY_DIR}:/work \
    $PFLOTRAN_SIF \
    $PFLOTRAN_EXE \
    -pflotranin /work/run${RUN_ID}/$SPIN_INPUT
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
MAIN_INPUT="pflotran-mcp19_run${RUN_ID}.in"

echo "Running main simulation: $MAIN_INPUT"

mpirun -np 4 singularity exec \
    --bind ${SENSITIVITY_DIR}:/work \
    $PFLOTRAN_SIF \
    $PFLOTRAN_EXE \
    -pflotranin /work/run${RUN_ID}/$MAIN_INPUT
MAIN_EXIT=$?

if [ $MAIN_EXIT -ne 0 ]; then
    echo "ERROR: Main simulation failed with exit code $MAIN_EXIT"
    echo "$RUN_ID MAIN_FAIL $MAIN_EXIT" >> "${SENSITIVITY_DIR}/failed_runs.log"
    exit 1
fi

echo "=========================================="
echo "Run $RUN_ID complete: $(date)"
echo "=========================================="
