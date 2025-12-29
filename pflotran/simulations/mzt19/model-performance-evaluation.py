#!/usr/bin/env python3
"""
PFLOTRAN Simulation Results Evaluator 

This script uses the Nash-Sutcliffe Efficiency metric (NSE) to evaluate PFLOTRAN model performance 

Requirements:
- pandas
- datetime
- os

File Structure Required:
├── bc_chem_data/           # Directory with CSV boundary condition files
├── TEMPLATE-constraint.txt # Chemistry constraint template
├── TEMPLATE-chemistry.txt  # Chemistry block template
├── TEMPLATE-pflotran-1d.in    # Main PFLOTRAN 1D template 
├── TEMPLATE-pflotran-spin-1d.in # 1D Spin-up template
├── hydro_us_*.txt         # Upstream hydrological data
└── hydro_ds_*.txt         # Downstream hydrological data

Usage:
    python pflotran_1d_generator.py [--year YEAR] [--ny NY] [--upstream_h H] [--downstream_h H]
    
Example:
    python pflotran_1d_generator.py --year 2019 --ny 108 --upstream_h 1.94 --downstream_h 1.66

Author: Christian Dewey
Date: 07.29.2025
Version: 0.1 - First implementation
"""

import os
import pandas as pd
import warnings
from datetime import datetime
import argparse
from typing import Dict, Tuple, List
from pathlib import Path
import shutil
import glob
import numpy as np

warnings.filterwarnings('ignore')


class PFLOTRANEvaluator:
    '''Main class for evaluating PFLOTRAN output'''

    def __init__(self, 
                 model_output_h5: str):
        
        self.model_output_h5 = model_output_h5

    def _calculate_NSE(self, 
                       model_output_df: pd.DataFrame, 
                       observations_df: pd.DataFrame) -> float:
        """Calculates the NSE metric"""

        mean_observations = observations_df.mean()
        denominator= np.sum( np.square(observations_df - mean_observations) )
        numerator = np.sum( np.square(observations_df - model_output_df) )

        nse = 1 - numerator / denominator

        return nse

    def run_nash_sutcliffe_efficiency_eval(self, 
                       component: str) -> float:
        """Runs the Nash-Sutcliffe evaluation for the specified component"""

        mean_observations = observations_df.mean()
        denominator= np.sum( np.square(observations_df - mean_observations) )
        numerator = np.sum( np.square(observations_df - model_output_df) )

        nse = 1 - numerator / denominator

        return nse


    #def evaluate(self):

