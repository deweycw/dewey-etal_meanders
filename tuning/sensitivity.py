"""
Sensitivity analysis using the Morris method for PFLOTRAN parameter screening.

The Morris method (Elementary Effects method) is a global sensitivity analysis
technique that identifies which parameters have:
- Large effects on the model output (high μ*)
- Nonlinear effects or interactions with other parameters (high σ)

This is an efficient screening method requiring O(k) simulations per trajectory
where k is the number of parameters.
"""

import logging
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import numpy as np
import pandas as pd
from dataclasses import dataclass, asdict

from .config import (
    PARAMETERS, PARAM_BY_NAME, get_parameter_names,
    get_parameter_bounds, get_default_values,
    transform_to_linear
)
from .simulation_runner import SimulationRunner
from .objective import ObjectiveFunction

logger = logging.getLogger(__name__)


@dataclass
class MorrisResult:
    """Results from Morris sensitivity analysis."""
    parameter_name: str
    mu: float  # Mean of elementary effects
    mu_star: float  # Mean of absolute elementary effects
    sigma: float  # Standard deviation of elementary effects
    elementary_effects: List[float]  # Individual EE values

    def to_dict(self) -> dict:
        return asdict(self)


class MorrisSensitivity:
    """
    Morris method sensitivity analysis for PFLOTRAN parameters.

    The Morris method generates trajectories through parameter space and
    computes elementary effects (local derivatives) at each point.
    """

    def __init__(self,
                 year: str,
                 meander: str,
                 param_names: Optional[List[str]] = None,
                 n_trajectories: int = 10,
                 n_levels: int = 4,
                 seed: Optional[int] = None,
                 output_dir: Optional[Path] = None):
        """
        Initialize Morris sensitivity analysis.

        Args:
            year: Simulation year
            meander: Meander identifier
            param_names: List of parameter names to analyze. If None, uses all.
            n_trajectories: Number of Morris trajectories (typically 10-20)
            n_levels: Number of levels in the parameter grid (typically 4-10)
            seed: Random seed for reproducibility
            output_dir: Directory to save results and checkpoints
        """
        self.year = year
        self.meander = meander
        self.param_names = param_names or get_parameter_names()
        self.n_params = len(self.param_names)
        self.n_trajectories = n_trajectories
        self.n_levels = n_levels

        if seed is not None:
            np.random.seed(seed)

        # Get parameter bounds (in log space)
        self.bounds = get_parameter_bounds(self.param_names, log_scale=True)

        # Output directory for checkpoints and results
        self.output_dir = output_dir or Path(f'sensitivity_{meander}_{year}')
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Initialize simulation runner and objective function
        self.runner = SimulationRunner(year=year, meander=meander)
        self.objective = ObjectiveFunction(year=year, meander=meander)

        # Storage for results
        self.trajectories: List[np.ndarray] = []
        self.objective_values: List[List[float]] = []
        self.elementary_effects: Dict[str, List[float]] = {
            name: [] for name in self.param_names
        }

    def generate_trajectories(self) -> List[np.ndarray]:
        """
        Generate Morris trajectories through parameter space.

        Each trajectory consists of (k+1) points where k is the number
        of parameters. Starting from a random point, each step changes
        exactly one parameter by a fixed delta.

        Returns:
            List of trajectories, each of shape (n_params+1, n_params)
        """
        self.trajectories = []

        # Grid step size
        delta = self.n_levels / (2 * (self.n_levels - 1))

        for t in range(self.n_trajectories):
            # Generate random starting point on grid
            start = np.random.randint(0, self.n_levels, self.n_params)
            start = start / (self.n_levels - 1)  # Normalize to [0, 1]

            # Ensure we can move in either direction
            start = np.clip(start, delta, 1 - delta)

            # Random permutation of parameter order
            perm = np.random.permutation(self.n_params)

            # Build trajectory
            trajectory = np.zeros((self.n_params + 1, self.n_params))
            trajectory[0] = start

            current = start.copy()
            for i, param_idx in enumerate(perm):
                # Random direction (+delta or -delta)
                direction = np.random.choice([-1, 1])
                current = current.copy()
                current[param_idx] += direction * delta

                # Clip to [0, 1]
                current[param_idx] = np.clip(current[param_idx], 0, 1)
                trajectory[i + 1] = current

            self.trajectories.append(trajectory)

        logger.info(f"Generated {self.n_trajectories} trajectories with "
                    f"{self.n_params + 1} points each")

        return self.trajectories

    def _grid_to_param_values(self, grid_point: np.ndarray) -> Dict[str, float]:
        """
        Convert a [0,1] grid point to actual parameter values.

        Args:
            grid_point: Array of values in [0, 1]

        Returns:
            Dictionary of parameter name -> value (in linear space)
        """
        # Scale from [0, 1] to bounds (in log space)
        log_values = self.bounds[:, 0] + grid_point * (self.bounds[:, 1] - self.bounds[:, 0])

        # Transform to linear space
        linear_values = transform_to_linear(log_values, self.param_names)

        return dict(zip(self.param_names, linear_values))

    def run_analysis(self,
                     checkpoint_interval: int = 10,
                     resume_from: Optional[Path] = None) -> List[MorrisResult]:
        """
        Run the full Morris sensitivity analysis.

        Args:
            checkpoint_interval: Save checkpoint every N simulations
            resume_from: Path to checkpoint file to resume from

        Returns:
            List of MorrisResult objects, sorted by μ* (descending)
        """
        if resume_from:
            self._load_checkpoint(resume_from)
        else:
            self.generate_trajectories()

        total_sims = self.n_trajectories * (self.n_params + 1)
        completed = sum(len(v) for v in self.objective_values)
        logger.info(f"Starting Morris analysis: {total_sims} simulations "
                    f"({completed} already completed)")

        sim_count = completed

        for traj_idx, trajectory in enumerate(self.trajectories):
            # Skip if trajectory already completed
            if traj_idx < len(self.objective_values) and \
               len(self.objective_values[traj_idx]) == len(trajectory):
                continue

            # Initialize objective values for this trajectory
            if traj_idx >= len(self.objective_values):
                self.objective_values.append([])

            traj_objectives = self.objective_values[traj_idx]

            for point_idx, grid_point in enumerate(trajectory):
                # Skip if already computed
                if point_idx < len(traj_objectives):
                    continue

                # Convert to parameter values
                param_values = self._grid_to_param_values(grid_point)

                # Run simulation
                run_id = f"morris_t{traj_idx:02d}_p{point_idx:02d}"
                logger.info(f"Running simulation {sim_count + 1}/{total_sims}: {run_id}")

                h5_path, metadata = self.runner.run_simulation(
                    param_values=param_values,
                    run_id=run_id,
                    keep_files=False
                )

                # Compute objective
                if h5_path is not None:
                    obj_value = self.objective.compute(h5_path)
                else:
                    obj_value = self.objective.penalty_value
                    logger.warning(f"Simulation {run_id} failed, using penalty value")

                traj_objectives.append(obj_value)
                sim_count += 1

                # Checkpoint
                if sim_count % checkpoint_interval == 0:
                    self._save_checkpoint()

            # Compute elementary effects for this trajectory
            self._compute_elementary_effects(traj_idx)

        # Save final results
        self._save_checkpoint()
        results = self._compute_summary()
        self._save_results(results)

        return results

    def _compute_elementary_effects(self, traj_idx: int):
        """Compute elementary effects for a single trajectory."""
        trajectory = self.trajectories[traj_idx]
        objectives = self.objective_values[traj_idx]

        if len(objectives) != len(trajectory):
            logger.warning(f"Incomplete trajectory {traj_idx}, skipping EE computation")
            return

        # Find which parameter changed at each step
        for i in range(len(trajectory) - 1):
            diff = trajectory[i + 1] - trajectory[i]
            changed_idx = np.argmax(np.abs(diff))
            delta = diff[changed_idx]

            if abs(delta) < 1e-10:
                continue

            # Elementary effect = (f(x+delta) - f(x)) / delta
            # But we normalize by bounds range
            param_name = self.param_names[changed_idx]
            param_range = self.bounds[changed_idx, 1] - self.bounds[changed_idx, 0]

            ee = (objectives[i + 1] - objectives[i]) / (delta * param_range)
            self.elementary_effects[param_name].append(ee)

    def _compute_summary(self) -> List[MorrisResult]:
        """Compute Morris sensitivity indices from elementary effects."""
        results = []

        for param_name in self.param_names:
            ee_values = self.elementary_effects[param_name]

            if len(ee_values) == 0:
                logger.warning(f"No elementary effects for {param_name}")
                results.append(MorrisResult(
                    parameter_name=param_name,
                    mu=np.nan,
                    mu_star=np.nan,
                    sigma=np.nan,
                    elementary_effects=[]
                ))
                continue

            ee_array = np.array(ee_values)

            results.append(MorrisResult(
                parameter_name=param_name,
                mu=float(np.mean(ee_array)),
                mu_star=float(np.mean(np.abs(ee_array))),
                sigma=float(np.std(ee_array)),
                elementary_effects=ee_values
            ))

        # Sort by μ* (descending)
        results.sort(key=lambda r: r.mu_star if not np.isnan(r.mu_star) else 0,
                     reverse=True)

        return results

    def _save_checkpoint(self):
        """Save current progress to checkpoint file."""
        checkpoint = {
            'timestamp': datetime.now().isoformat(),
            'year': self.year,
            'meander': self.meander,
            'param_names': self.param_names,
            'n_trajectories': self.n_trajectories,
            'n_levels': self.n_levels,
            'trajectories': [t.tolist() for t in self.trajectories],
            'objective_values': self.objective_values,
            'elementary_effects': self.elementary_effects,
            'bounds': self.bounds.tolist(),
        }

        checkpoint_path = self.output_dir / 'checkpoint.json'
        with open(checkpoint_path, 'w') as f:
            json.dump(checkpoint, f, indent=2)

        logger.info(f"Saved checkpoint to {checkpoint_path}")

    def _load_checkpoint(self, checkpoint_path: Path):
        """Load progress from checkpoint file."""
        with open(checkpoint_path) as f:
            checkpoint = json.load(f)

        self.param_names = checkpoint['param_names']
        self.n_params = len(self.param_names)
        self.n_trajectories = checkpoint['n_trajectories']
        self.n_levels = checkpoint['n_levels']
        self.trajectories = [np.array(t) for t in checkpoint['trajectories']]
        self.objective_values = checkpoint['objective_values']
        self.elementary_effects = checkpoint['elementary_effects']
        self.bounds = np.array(checkpoint['bounds'])

        logger.info(f"Loaded checkpoint from {checkpoint_path}")

    def _save_results(self, results: List[MorrisResult]):
        """Save final results to files."""
        # Save as JSON
        results_dict = {
            'timestamp': datetime.now().isoformat(),
            'year': self.year,
            'meander': self.meander,
            'n_trajectories': self.n_trajectories,
            'n_levels': self.n_levels,
            'results': [r.to_dict() for r in results]
        }

        json_path = self.output_dir / 'morris_results.json'
        with open(json_path, 'w') as f:
            json.dump(results_dict, f, indent=2)

        # Save as CSV for easy viewing
        df = pd.DataFrame([{
            'parameter': r.parameter_name,
            'mu': r.mu,
            'mu_star': r.mu_star,
            'sigma': r.sigma,
            'n_effects': len(r.elementary_effects)
        } for r in results])

        csv_path = self.output_dir / 'morris_results.csv'
        df.to_csv(csv_path, index=False)

        logger.info(f"Saved results to {json_path} and {csv_path}")

    def get_influential_parameters(self,
                                    threshold_quantile: float = 0.5) -> List[str]:
        """
        Get list of influential parameters based on μ* threshold.

        Args:
            threshold_quantile: Keep parameters with μ* above this quantile

        Returns:
            List of parameter names sorted by influence (most influential first)
        """
        results = self._compute_summary()

        # Get μ* values
        mu_stars = [r.mu_star for r in results if not np.isnan(r.mu_star)]

        if not mu_stars:
            return []

        threshold = np.quantile(mu_stars, threshold_quantile)

        influential = [r.parameter_name for r in results
                       if not np.isnan(r.mu_star) and r.mu_star >= threshold]

        return influential


def run_morris_analysis(year: str = '2019',
                        meander: str = 'mzt',
                        n_trajectories: int = 10,
                        output_dir: Optional[Path] = None,
                        **kwargs) -> List[MorrisResult]:
    """
    Convenience function to run Morris sensitivity analysis.

    Args:
        year: Simulation year
        meander: Meander identifier
        n_trajectories: Number of trajectories
        output_dir: Output directory
        **kwargs: Additional arguments to MorrisSensitivity

    Returns:
        List of MorrisResult objects sorted by μ*
    """
    morris = MorrisSensitivity(
        year=year,
        meander=meander,
        n_trajectories=n_trajectories,
        output_dir=output_dir,
        **kwargs
    )

    return morris.run_analysis()
