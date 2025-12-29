# %%
import os
import pandas as pd
import numpy as np
from pathlib import Path

# Get the directory containing this script for relative path resolution
SCRIPT_DIR = Path(__file__).parent.resolve()
BUILD_DIR = SCRIPT_DIR.parent  # pflotran/build directory

'''
import bc concentrations and interpolate

'''
def write_regions(nx:int):

    region_text = ""

    for ix in range(0,nx):

        region_text = region_text + f"\nREGION top_bc_reg_{ix}\n  FILE xxgrid010-top.h5\n/"

    return region_text


def write_flow_conditions(nx:int, upstream_h:float, downstream_h:float, input_dir: str):

    flow_conditions_text = ""

    dh = (upstream_h - downstream_h) / nx 

    hx = upstream_h

    for ix in range(0,nx):

        hx = hx -dh 
        
        flow_conditions_text = flow_conditions_text + f"\nFLOW_CONDITION top_bc_{ix}\n  TYPE\n    LIQUID_PRESSURE seepage\n  /\n  CYCLIC\n  DATUM 0.d0 0.d0 {hx:.3f}d0\n  LIQUID_PRESSURE 101325.d0\n/"
        
    return flow_conditions_text


def write_bc_blocks(nx: int):

    bc_text = ""

    for ix in range(0,nx):

        bc_text = bc_text + f'\nBOUNDARY_CONDITION top_{ix}\n  FLOW_CONDITION top_bc_{ix}\n  TRANSPORT_CONDITION from_top\n  REGION top_bc_reg_{ix}\n/'

    return bc_text


def assemble_pflotran_input(input_dir: str, save_dir: str, fname: str, spin_number: int):

    if spin_number == 1:
        with open(input_dir + 'pflotran-spin-TEMP-3-spin1.in','r') as file:
            chunk3 = file.readlines()
        with open(input_dir + 'pflotran-spin-TEMP-1-spin1.in','r') as file:
            chunk1 = file.readlines()
    elif spin_number == 2 :
        with open(input_dir + 'pflotran-spin-TEMP-3-spin2.in','r') as file:
            chunk3 = file.readlines()
        with open(input_dir + 'pflotran-spin-TEMP-1-spin2.in','r') as file:
            chunk1 = file.readlines()

    region_block = write_regions(nx=108)

    with open(input_dir + 'pflotran-spin-TEMP-2.in','r') as file:
        chunk2 = file.readlines()

    flow_conditions_block = write_flow_conditions(nx=108, upstream_h=1.84, downstream_h=1.46, input_dir=input_dir)

    bc_block = write_bc_blocks(nx=108)

    with open(input_dir + 'pflotran-spin-TEMP-4.in','r') as file:
        chunk4 = file.readlines()

    if os.path.exists(save_dir + fname):
        os.remove(save_dir + fname)

    with open(save_dir + fname,'a') as file:
        file.writelines(chunk1)
        file.writelines(region_block)
        file.writelines(chunk2)
        file.writelines(flow_conditions_block)
        file.writelines(chunk3)
        file.writelines(bc_block)       
        file.writelines(chunk4)
    



if __name__ == '__main__':
    # Use relative paths based on script location
    input_dir = str(SCRIPT_DIR / 'mzt-18') + '/'
    save_dir = str(SCRIPT_DIR / 'mzt-18') + '/'

    for spin_number in [1, 2]:
        fname = f'pflotran-spin-{spin_number}-n.in'
        assemble_pflotran_input(input_dir, save_dir, fname, spin_number)

