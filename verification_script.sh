#!/bin/bash
# save as benchmark_pflotran.sh

INPUT="/home/christiandewey/Code/dewey-etal_meanders/pflotran/simulations/mzt19/2026-01-30/benchmark/benchmark.in"
RESULTS="benchmark_results.txt"

echo "PFLOTRAN MPI Scaling Benchmark" > $RESULTS
echo "==============================" >> $RESULTS
echo "" >> $RESULTS

# Test P-cores only (cores 0-11)
for NP in 4 6 8 10 12; do
    echo "Testing $NP ranks on P-cores..."
    START=$(date +%s.%N)
    mpirun -np $NP --cpu-set 0-11 --bind-to core $PFLOTRAN_DIR/src/pflotran/pflotran -pflotranin $INPUT > /dev/null 2>&1
    END=$(date +%s.%N)
    ELAPSED=$(echo "$END - $START" | bc)
    echo "$NP ranks (P-cores only): ${ELAPSED}s" >> $RESULTS
    echo "$NP ranks: ${ELAPSED}s"
done

# Test all cores for comparison
for NP in 14 16 20; do
    echo "Testing $NP ranks on all cores..."
    START=$(date +%s.%N)
    mpirun -np $NP --bind-to core $PFLOTRAN_DIR/src/pflotran/pflotran -pflotranin $INPUT > /dev/null 2>&1
    END=$(date +%s.%N)
    ELAPSED=$(echo "$END - $START" | bc)
    echo "$NP ranks (all cores): ${ELAPSED}s" >> $RESULTS
    echo "$NP ranks: ${ELAPSED}s"
done

cat $RESULTS
