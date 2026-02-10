#!/bin/bash
#SBATCH --job-name=sa_trans_only
#SBATCH --ntasks=4
#SBATCH --partition=standard
#SBATCH --time=02:00:00
#SBATCH --output=logs/run%03a.out
#SBATCH --error=logs/run%03a.err
#SBATCH --mail-type=ALL
#SBATCH --mail-user=cdewey@udel.edu

# Submit script for runs with COMPLETE SPIN but INCOMPLETE TRANSIENT.
# Skips spin-up and runs only the main transient simulation.
#
# Usage: bash submit_trans_only.sh
#   The script scans run directories, identifies runs needing only transient,
#   and submits itself as a SLURM array job.

# ============================================================
# If not running under SLURM, scan runs and submit
# ============================================================
if [ -z "$SLURM_ARRAY_TASK_ID" ]; then
    SPIN_SIZE_MIN=48000000    # ~49 MB threshold for complete spin
    TRANS_SIZE_MIN=700000000  # ~731 MB threshold for complete transient

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

        # Check transient .h5 file size
        trans_h5=$(ls "${run_dir}"/pflotran-*.h5 2>/dev/null | grep -v spin | head -1)
        trans_ok=false
        if [[ -f "$trans_h5" ]]; then
            trans_size=$(stat -c%s "$trans_h5" 2>/dev/null || stat -f%z "$trans_h5" 2>/dev/null)
            [[ $trans_size -ge $TRANS_SIZE_MIN ]] && trans_ok=true
        fi

        # Spin finished but transient not
        if $spin_ok && ! $trans_ok; then
            run_ids+=("$((10#$id))")
        fi
    done

    if [ ${#run_ids[@]} -eq 0 ]; then
        echo "No runs need transient-only resubmission. Nothing to submit."
        exit 0
    fi

    ARRAY_SPEC=$(IFS=,; echo "${run_ids[*]}")
    echo "Submitting ${#run_ids[@]} runs needing transient only:"
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
echo "Mode:       transient only (spin already complete)"
echo "Start time: $(date)"
echo "=========================================="

# ============================================================
# Main simulation (skip spin-up)
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
