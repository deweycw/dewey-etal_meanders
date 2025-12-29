#!/bin/bash

clear 

source /home/christiandewey/Code/dewey-etal-meanders/env/bin/activate

sleep 1 
echo "............writing 1D simulation files............"
sleep 1 
PYTHON_OUTPUT=$(./pflotran_generator_1d.py)
SPIN_FILE=$(echo "$PYTHON_OUTPUT" | tail -1)

sleep 1 
echo "............starting 1D spin up............"
sleep 1
mpirun -n 6 /home/christiandewey/Code/pflotran/src/pflotran/pflotran -pflotranin $SPIN_FILE

sleep 1 
echo "............plotting 1D spin up............"
sleep 1 
SPIN_H5OUT="${SPIN_FILE%.in}.h5"
echo $SPIN_H5OUT
python plot-obs-sim.py --year 2019 --meander mz --plot-average True --dim 1D $SPIN_H5OUT
SPIN_PDF="${SPIN_FILE%.in}.pdf"


sleep 2 
echo "............starting 1D transient simulation............"
sleep 1
substr_del=_spin
SIM_FILE=$(echo "$SPIN_FILE" | sed "s/$substr_del//")
mpirun -n 6 /home/christiandewey/Code/pflotran/src/pflotran/pflotran -pflotranin $SIM_FILE

sleep 1 
echo "............plotting 1D transiet simulation............"
sleep 1 
SIM_H5OUT="${SIM_FILE%.in}.h5"
python plot-obs-sim.py --year 2019 --meander mz --plot-average False --dim 1D $SIM_H5OUT
SIM_PDF="${SIM_FILE%.in}.pdf"

sleep 1 
echo "............output files............"
sleep 1 
echo $SPIN_PDF
echo $SIM_PDF