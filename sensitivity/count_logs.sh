#!/bin/bash
# Count occurrences of 'Wall Clock Time' in each run log
# and report any with more than 2.

LOG_DIR="/home/4315/sensitivity/logs"

echo "Logs with > 2 'Wall Clock Time' occurrences:"
echo "============================================="

count_gt2=0
for log in "$LOG_DIR"/run*.out; do
    n=$(grep -c 'Wall Clock Time' "$log")
    if [ "$n" -gt 2 ]; then
        echo "$(basename $log): $n occurrences"
        count_gt2=$((count_gt2 + 1))
    fi
done

if [ "$count_gt2" -eq 0 ]; then
    echo "None found."
fi

echo ""
echo "Total logs with > 2 occurrences: $count_gt2"

