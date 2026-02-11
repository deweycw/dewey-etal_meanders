#!/bin/bash
# Check completion status and wall times for sensitivity runs
# Run from sensitivity/ directory

SPIN_SIZE_MIN=48000000    # ~49 MB threshold for complete spin
TRANS_SIZE_MIN=700000000  # ~731 MB threshold for complete transient

printf "%-8s %-6s %-6s %8s %8s %8s\n" "Run" "Spin" "Trans" "Spin" "Trans" "Total"
printf "%s\n" "------------------------------------------------"

complete=0
incomplete=0

for run_dir in run[0-9][0-9][0-9]; do
    run_name="${run_dir}"
    spin_ok="NO"
    trans_ok="NO"
    spin_hr="-"
    trans_hr="-"
    total_hr="-"

    # Check spin .h5 file size
    spin_h5=$(ls "${run_dir}"/pflotran-*_spin.h5 2>/dev/null | head -1)
    if [[ -f "$spin_h5" ]]; then
        spin_size=$(stat -c%s "$spin_h5" 2>/dev/null || stat -f%z "$spin_h5" 2>/dev/null)
        [[ $spin_size -ge $SPIN_SIZE_MIN ]] && spin_ok="OK"
    fi

    # Check transient .h5 file size (not spin)
    trans_h5=$(ls "${run_dir}"/pflotran-*.h5 2>/dev/null | grep -v spin | head -1)
    if [[ -f "$trans_h5" ]]; then
        trans_size=$(stat -c%s "$trans_h5" 2>/dev/null || stat -f%z "$trans_h5" 2>/dev/null)
        [[ $trans_size -ge $TRANS_SIZE_MIN ]] && trans_ok="OK"
    fi

    # Check log file for wall times
    log_file="logs/${run_name}.out"
    if [[ -f "$log_file" ]]; then
        # Get all wall clock times from the log
        wall_times=$(grep "Wall Clock Time" "$log_file" | awk '{print $8}')
        n_times=$(echo "$wall_times" | grep -c .)

        if [[ $n_times -ge 2 ]]; then
            # Both spin and transient completed
            spin_dec=$(echo "$wall_times" | tail -2 | head -1)
            trans_dec=$(echo "$wall_times" | tail -1)
            total_dec=$(awk "BEGIN {print $spin_dec + $trans_dec}")
            spin_hr=$(awk "BEGIN {h=int($spin_dec); m=int(($spin_dec-h)*60); printf \"%d:%02d\", h, m}")
            trans_hr=$(awk "BEGIN {h=int($trans_dec); m=int(($trans_dec-h)*60); printf \"%d:%02d\", h, m}")
            total_hr=$(awk "BEGIN {h=int($total_dec); m=int(($total_dec-h)*60); printf \"%d:%02d\", h, m}")
        elif [[ $n_times -eq 1 ]]; then
            # Only spin completed
            spin_dec=$(echo "$wall_times" | tail -1)
            spin_hr=$(awk "BEGIN {h=int($spin_dec); m=int(($spin_dec-h)*60); printf \"%d:%02d\", h, m}")
        fi
    fi

    # Count complete/incomplete
    if [[ "$spin_ok" == "OK" && "$trans_ok" == "OK" ]]; then
        ((complete++))
    else
        ((incomplete++))
    fi

    printf "%-8s %-6s %-6s %8s %8s %8s\n" "$run_name" "$spin_ok" "$trans_ok" "$spin_hr" "$trans_hr" "$total_hr"

done

printf "%s\n" "------------------------------------------------"
printf "Complete: %d   Incomplete: %d\n" "$complete" "$incomplete"
