#!/bin/bash
# Detect failed Morris sensitivity analysis runs.
# Writes results to failed_runs.log

SENSITIVITY_DIR="/lustre/dewey/users/4315/sensitivity"
LOG_DIR="${SENSITIVITY_DIR}/logs"
OUTPUT="${SENSITIVITY_DIR}/failed_runs.log"

> "$OUTPUT"  # clear existing log

n_total=0
n_failed=0
n_spin_fail=0
n_main_fail=0
n_no_log=0

for i in $(seq 0 339); do
    RUN_ID=$(printf '%03d' $i)
    LOG_FILE="${LOG_DIR}/run${RUN_ID}.out"
    n_total=$((n_total + 1))

    if [ ! -f "$LOG_FILE" ]; then
        echo "${RUN_ID} NO_LOG" >> "$OUTPUT"
        n_failed=$((n_failed + 1))
        n_no_log=$((n_no_log + 1))
        continue
    fi

    completions=$(grep -c 'Wall Clock Time' "$LOG_FILE")

    if [ "$completions" -ge 2 ]; then
        continue  # success
    elif [ "$completions" -eq 1 ]; then
        echo "${RUN_ID} MAIN_FAIL" >> "$OUTPUT"
        n_failed=$((n_failed + 1))
        n_main_fail=$((n_main_fail + 1))
    else
        echo "${RUN_ID} SPIN_FAIL" >> "$OUTPUT"
        n_failed=$((n_failed + 1))
        n_spin_fail=$((n_spin_fail + 1))
    fi
done

echo "=============================="
echo "Total runs:     $n_total"
echo "Successful:     $((n_total - n_failed))"
echo "Failed:         $n_failed ($(( 100 * n_failed / n_total ))%)"
echo "  Spin failures:  $n_spin_fail"
echo "  Main failures:  $n_main_fail"
echo "  No log file:    $n_no_log"
echo "=============================="
echo "Results written to $OUTPUT"
