#!/bin/bash
#SBATCH --job-name=sa_spin_trans
#SBATCH --ntasks=4
#SBATCH --partition=standard
#SBATCH --time=04:00:00
#SBATCH --output=logs/run%03a.out
#SBATCH --error=logs/run%03a.err
#SBATCH --mail-type=ALL
#SBATCH --mail-user=cdewey@udel.edu

# Submit script for runs with INCOMPLETE SPIN (and therefore incomplete transient).
# Runs both spin-up and main transient simulation.
#
# Usage: bash submit_spin_trans.sh
#   The script scans run directories, identifies runs needing spin + transient,
#   and submits itself as a SLURM array job.

# ============================================================
# If not running under SLURM, scan runs and submit
# ============================================================
if [ -z "$SLURM_ARRAY_TASK_ID" ]; then
    SPIN_SIZE_MIN=48000000    # ~49 MB threshold for complete spin

    run_ids=()
    for run_dir in run[0-9][0-9][0-9]; do
        id="${run_dir#run}"
        # Check spin .h5 file size
        spin_h5=$(ls "${run_dir}"/pflotran-*_spin.h5 2>/dev/null | head -1)
        spin_ok=false
        if [[ -f "$spin_h5" ]]; then
            spin_size=$(stat -c%s "$spin_h5" 2>/dev/null || stat -f%z "$spin_h5" 2>/dev/null)
            [[ $spin_size -ge $SPIN_SIZE_MIN ]] && spin_ok=true
        fi

        if ! $spin_ok; then
            # Strip leading zeros for SLURM array spec
            run_ids+=("$((10#$id))")
        fi
    done

    if [ ${#run_ids[@]} -eq 0 ]; then
        echo "No runs need spin + transient. Nothing to submit."
        exit 0
    fi

    ARRAY_SPEC=$(IFS=,; echo "${run_ids[*]}")
    echo "Submitting ${#run_ids[@]} runs needing spin + transient:"
    echo "  Array indices: $ARRAY_SPEC"
    sbatch --array="${ARRAY_SPEC}%32" "$0"
    exit $?
fi

# ============================================================
# SLURM job starts here
# ============================================================

# Load modules
vpkg_require openmpi
vpkg_require singularity

# Paths
SENSITIVITY_DIR="/lustre/dewey/users/4315/sensitivity"
PFLOTRAN_SIF="/lustre/dewey/sw/pflotran.sif"
PFLOTRAN_EXE="/pflotran/src/pflotran/pflotran"

# Construct run directory from task ID
RUN_ID=$(printf '%03d' $SLURM_ARRAY_TASK_ID)
RUN_DIR="${SENSITIVITY_DIR}/run${RUN_ID}"

cd "$RUN_DIR" || { echo "ERROR: Cannot cd to $RUN_DIR"; exit 1; }

echo "=========================================="
echo "Task ID:    $SLURM_ARRAY_TASK_ID"
echo "Run ID:     $RUN_ID"
echo "Mode:       spin + transient"
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
