#!/bin/bash

clear 

echo "............writing 2D simulation files............"
sleep 1 
spin_file=`python ./xsection-make-mzt19-input.py`

echo "............starting 2D spin up............"
sleep 1
mpirun -n 12 /home/christiandewey/Code/pflotran/src/pflotran/pflotran -pflotranin $spin_file

echo "............plotting 2D spin up............"
sleep 1 
spin_h5output="${spin_file%.in}.h5"
python obs_v_sim.py $spin_h5output
spin_pdf="${spin_file%.in}.pdf"

echo "............starting 2D transient simulation............"
sleep 1
substr_del=spin-
sim_file=$(echo "$spin_file" | sed "s/$substr_del//")
mpirun -n 12 /home/christiandewey/Code/pflotran/src/pflotran/pflotran -pflotranin $sim_file

echo "............plotting 2D transiet simulation............"
sleep 1 
sim_h5output="${sim_file%.in}.h5"
python obs_v_sim.py $sim_h5output
sim_pdf="${sim_file%.in}.pdf"

echo "............output files............"
sleep 1 
echo $spin_pdf
echo $sim_pdf 