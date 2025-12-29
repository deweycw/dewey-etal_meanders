#!/bin/bash

clear 
echo "............starting 1D simulation............"
sleep 1 
in_file=`python ./make1d.py`
mpirun -n 12 /home/christiandewey/Code/pflotran/src/pflotran/pflotran -pflotranin $in_file
echo "............plotting 1D simulation............"
sleep 1 
h5output="${in_file%.in}.h5"
python obs_v_sim.py $h5output
pdf="${in_file%.in}.pdf"
sleep 1
echo "............saving pdf............"
echo "pdf: $pdf"