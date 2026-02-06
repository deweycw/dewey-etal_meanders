"""
Objective function computation for PFLOTRAN parameter tuning.

This module provides functions to:
- Load simulation results using PflotranProcessor
- Load observational data
- Compute weighted KGE-based objective function
"""

import logging
from pathlib import Path
from typing import Dict, Optional, Union, Any
import numpy as np
import pandas as pd

# Import PflotranProcessor - adjust path as needed
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
from processing.pflotran import PflotranProcessor

from .config import SIMULATION_CONFIGS, SPECIES_WEIGHTS, get_species_for_meander

logger = logging.getLogger(__name__)


class ObjectiveFunction:
    """
    Compute objective function for PFLOTRAN parameter tuning.

    The objective combines KGE metrics across multiple chemical species,
    weighted by data availability and species importance.
    """

    DEFAULT_DATA_DIR = Path('/home/christiandewey/Code/dewey-etal_meanders/data/observational/porewater')

    def __init__(self,
                 year: str,
                 meander: str,
                 obs_data_dir: Optional[Path] = None,
                 penalty_value: float = 2.0):
        """
        Initialize the objective function.

        Args:
            year: Simulation year ('2018' or '2019')
            meander: Meander identifier ('mzt' or 'mcp')
            obs_data_dir: Directory containing observational data CSV files
            penalty_value: Value to assign for failed simulations or missing data
        """
        self.year = year
        self.meander = meander.lower()
        self.penalty_value = penalty_value

        # Get config
        config_key = (year, self.meander)
        if config_key not in SIMULATION_CONFIGS:
            raise ValueError(f"Invalid year/meander: {config_key}")
        self.sim_config = SIMULATION_CONFIGS[config_key]

        # Load observational data
        self.obs_data_dir = obs_data_dir or self.DEFAULT_DATA_DIR
        self.chem_obs = self._load_observations()

        # Start date for simulations
        self.startdate = np.datetime64(self.sim_config['startdate'])

        # Meander code for processor
        self.meander_code = 'MZ' if 'mz' in self.meander else 'MC'

        # Get meander-specific species list for tuning
        self.tuning_species = get_species_for_meander(self.meander)

    def _load_observations(self) -> pd.DataFrame:
        """Load observational porewater chemistry data."""
        # Construct filename
        meander_prefix = 'mz' if 'mz' in self.meander else 'mc'
        filename = f'{meander_prefix}_{self.year}_porewater.csv'
        filepath = self.obs_data_dir / filename

        if not filepath.exists():
            raise FileNotFoundError(f"Observational data not found: {filepath}")

        # Load CSV
        df = pd.read_csv(filepath)

        # Parse dates - handle different date formats
        if 'Date' in df.columns:
            df['Date'] = pd.to_datetime(df['Date'], format='mixed')

        logger.info(f"Loaded {len(df)} observations from {filename}")
        return df

    def compute(self,
                h5_path: Union[str, Path],
                return_details: bool = False) -> Union[float, Dict[str, Any]]:
        """
        Compute the objective function for a simulation result.

        Args:
            h5_path: Path to the simulation HDF5 output file
            return_details: If True, return detailed breakdown of metrics

        Returns:
            If return_details is False, returns the scalar objective value
            (lower is better). If return_details is True, returns a dictionary
            with the objective value and per-species metrics.
        """
        h5_path = Path(h5_path)

        if not h5_path.exists():
            logger.error(f"HDF5 file not found: {h5_path}")
            if return_details:
                return {'objective': self.penalty_value, 'error': 'File not found'}
            return self.penalty_value

        try:
            # Initialize processor
            processor = PflotranProcessor(
                h5_path=str(h5_path),
                meander=self.meander_code,
                perpendicular_axis='x'
            )

            # Calculate KGE for all components
            kge_results = processor.calculate_kge(
                startdate=self.startdate,
                chem_obs=self.chem_obs,
                print_summary=False
            )

            # Extract summary DataFrame
            summary_df = kge_results['summary']

            # Compute weighted objective
            objective, species_metrics = self._compute_weighted_objective(summary_df)

            if return_details:
                return {
                    'objective': objective,
                    'species_metrics': species_metrics,
                    'summary': summary_df,
                    'n_components': kge_results['n_components']
                }

            return objective

        except Exception as e:
            logger.exception(f"Error computing objective for {h5_path}: {e}")
            if return_details:
                return {'objective': self.penalty_value, 'error': str(e)}
            return self.penalty_value

    def _compute_weighted_objective(self,
                                     summary_df: pd.DataFrame) -> tuple:
        """
        Compute weighted objective from KGE summary.

        Uses sqrt(n_observations) and species importance weights.
        Only includes species specified for this meander.

        Args:
            summary_df: DataFrame with columns [Component, Obs, KGE, NSE, RMSE, r, α, β, n]

        Returns:
            Tuple of (objective_value, species_metrics_dict)
        """
        species_metrics = {}
        weighted_losses = []
        total_weight = 0

        for _, row in summary_df.iterrows():
            obs_name = row.get('Obs', row.get('Component', 'Unknown'))

            # Skip species not in the meander's tuning list
            if obs_name not in self.tuning_species:
                continue

            # Get observation count
            n_obs = row.get('n', 1)
            if pd.isna(n_obs) or n_obs == 0:
                n_obs = 1

            # Get KGE value
            kge = row.get('KGE', np.nan)
            if pd.isna(kge):
                kge_loss = self.penalty_value
            else:
                # KGE loss: transform so lower is better
                # KGE = 1 is perfect, KGE < -0.41 is worse than climatology
                kge_loss = 1.0 - kge

            # Compute weight
            data_weight = np.sqrt(n_obs)  # Weight by data availability
            importance_weight = SPECIES_WEIGHTS.get(obs_name, 0.5)  # Species importance
            weight = data_weight * importance_weight

            weighted_losses.append(weight * kge_loss)
            total_weight += weight

            # Store metrics
            species_metrics[obs_name] = {
                'KGE': kge,
                'KGE_loss': kge_loss,
                'n_obs': n_obs,
                'weight': weight,
                'weighted_loss': weight * kge_loss,
                'NSE': row.get('NSE', np.nan),
                'RMSE': row.get('RMSE', np.nan),
                'r': row.get('r', np.nan),
            }

        # Normalize by total weight
        if total_weight > 0:
            objective = sum(weighted_losses) / total_weight
        else:
            objective = self.penalty_value

        return objective, species_metrics


def compute_objective(h5_path: Union[str, Path],
                      year: str = '2019',
                      meander: str = 'mzt',
                      **kwargs) -> float:
    """
    Convenience function to compute objective for a simulation.

    Args:
        h5_path: Path to simulation HDF5 results
        year: Simulation year
        meander: Meander identifier
        **kwargs: Additional arguments to ObjectiveFunction

    Returns:
        Objective function value (lower is better)
    """
    obj_func = ObjectiveFunction(year=year, meander=meander, **kwargs)
    return obj_func.compute(h5_path)


def compute_objective_with_details(h5_path: Union[str, Path],
                                    year: str = '2019',
                                    meander: str = 'mzt',
                                    **kwargs) -> Dict[str, Any]:
    """
    Compute objective with detailed per-species breakdown.

    Args:
        h5_path: Path to simulation HDF5 results
        year: Simulation year
        meander: Meander identifier
        **kwargs: Additional arguments to ObjectiveFunction

    Returns:
        Dictionary with objective value and detailed metrics
    """
    obj_func = ObjectiveFunction(year=year, meander=meander, **kwargs)
    return obj_func.compute(h5_path, return_details=True)
