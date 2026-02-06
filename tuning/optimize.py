"""
Bayesian optimization for PFLOTRAN parameter tuning.

Uses Gaussian Process surrogate modeling with Expected Improvement
acquisition function to efficiently search the parameter space.
"""

import logging
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
import numpy as np
import pandas as pd
from dataclasses import dataclass, asdict

try:
    from scipy.optimize import minimize
    from scipy.stats import norm
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

try:
    from sklearn.gaussian_process import GaussianProcessRegressor
    from sklearn.gaussian_process.kernels import Matern, ConstantKernel, WhiteKernel
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False

from .config import (
    PARAM_BY_NAME, get_parameter_names,
    get_parameter_bounds, get_default_values,
    transform_to_linear, transform_to_log
)
from .simulation_runner import SimulationRunner
from .objective import ObjectiveFunction

logger = logging.getLogger(__name__)


@dataclass
class OptimizationResult:
    """Result from a single optimization iteration."""
    iteration: int
    param_values: Dict[str, float]  # Parameter values in linear space
    param_values_log: Dict[str, float]  # Parameter values in log space
    objective: float
    acquisition_value: float
    is_best: bool
    timestamp: str

    def to_dict(self) -> dict:
        return asdict(self)


class BayesianOptimizer:
    """
    Bayesian optimization using Gaussian Process surrogate.

    Uses the Expected Improvement (EI) acquisition function to balance
    exploration and exploitation.
    """

    def __init__(self,
                 year: str,
                 meander: str,
                 param_names: Optional[List[str]] = None,
                 n_initial: int = 5,
                 output_dir: Optional[Path] = None,
                 seed: Optional[int] = None):
        """
        Initialize Bayesian optimizer.

        Args:
            year: Simulation year
            meander: Meander identifier
            param_names: List of parameter names to optimize. If None, uses all.
            n_initial: Number of initial random samples before GP fitting
            output_dir: Directory for results and checkpoints
            seed: Random seed for reproducibility
        """
        if not HAS_SKLEARN:
            raise ImportError("scikit-learn is required for Bayesian optimization. "
                              "Install with: pip install scikit-learn")
        if not HAS_SCIPY:
            raise ImportError("scipy is required for Bayesian optimization. "
                              "Install with: pip install scipy")

        self.year = year
        self.meander = meander
        self.param_names = param_names or get_parameter_names()
        self.n_params = len(self.param_names)
        self.n_initial = n_initial

        if seed is not None:
            np.random.seed(seed)
            self.seed = seed
        else:
            self.seed = None

        # Get parameter bounds (in log space for optimization)
        self.bounds = get_parameter_bounds(self.param_names, log_scale=True)

        # Output directory
        self.output_dir = output_dir or Path(f'optimize_{meander}_{year}')
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Initialize components
        self.runner = SimulationRunner(year=year, meander=meander)
        self.objective_func = ObjectiveFunction(year=year, meander=meander)

        # Gaussian Process surrogate
        self._init_gp()

        # Storage for optimization history
        self.X: List[np.ndarray] = []  # Parameter values (log space)
        self.y: List[float] = []  # Objective values
        self.results: List[OptimizationResult] = []
        self.best_objective = np.inf
        self.best_params: Optional[Dict[str, float]] = None

    def _init_gp(self):
        """Initialize the Gaussian Process surrogate model."""
        # Matern 5/2 kernel with automatic relevance determination
        kernel = (
            ConstantKernel(1.0, (1e-3, 1e3)) *
            Matern(length_scale=np.ones(self.n_params),
                   length_scale_bounds=(1e-2, 1e2),
                   nu=2.5) +
            WhiteKernel(noise_level=0.1, noise_level_bounds=(1e-5, 1e1))
        )

        self.gp = GaussianProcessRegressor(
            kernel=kernel,
            n_restarts_optimizer=10,
            normalize_y=True,
            random_state=self.seed
        )

    def _log_to_param_dict(self, x_log: np.ndarray) -> Dict[str, float]:
        """Convert log-space array to parameter dictionary (linear space)."""
        x_linear = transform_to_linear(x_log, self.param_names)
        return dict(zip(self.param_names, x_linear))

    def _param_dict_to_log(self, params: Dict[str, float]) -> np.ndarray:
        """Convert parameter dictionary to log-space array."""
        values = np.array([params[name] for name in self.param_names])
        return transform_to_log(values, self.param_names)

    def expected_improvement(self, X: np.ndarray, xi: float = 0.01) -> np.ndarray:
        """
        Compute Expected Improvement acquisition function.

        Args:
            X: Points to evaluate, shape (n_points, n_params)
            xi: Exploration-exploitation trade-off parameter

        Returns:
            EI values at each point
        """
        if len(self.y) < self.n_initial:
            # Not enough data for GP, return random exploration
            return np.random.rand(len(X))

        # Get GP predictions
        mu, sigma = self.gp.predict(X, return_std=True)

        # Best observed value (we're minimizing)
        f_best = np.min(self.y)

        # Compute EI
        with np.errstate(divide='warn'):
            imp = f_best - mu - xi
            Z = imp / sigma
            ei = imp * norm.cdf(Z) + sigma * norm.pdf(Z)
            ei[sigma == 0.0] = 0.0

        return ei

    def _select_next_point(self, n_restarts: int = 20) -> np.ndarray:
        """
        Select the next point to evaluate by maximizing EI.

        Args:
            n_restarts: Number of random restarts for optimization

        Returns:
            Next point to evaluate (in log space)
        """
        if len(self.X) < self.n_initial:
            # Random sampling for initial points
            return self._random_sample()

        # Optimize EI
        best_x = None
        best_ei = -np.inf

        for _ in range(n_restarts):
            # Random starting point
            x0 = self._random_sample()

            # Optimize EI (maximize, so negate for minimize)
            result = minimize(
                lambda x: -self.expected_improvement(x.reshape(1, -1))[0],
                x0,
                bounds=list(zip(self.bounds[:, 0], self.bounds[:, 1])),
                method='L-BFGS-B'
            )

            if -result.fun > best_ei:
                best_ei = -result.fun
                best_x = result.x

        return best_x

    def _random_sample(self) -> np.ndarray:
        """Generate a random point within bounds."""
        return np.random.uniform(self.bounds[:, 0], self.bounds[:, 1])

    def run_optimization(self,
                         n_iterations: int,
                         checkpoint_interval: int = 5,
                         resume_from: Optional[Path] = None) -> Dict[str, Any]:
        """
        Run Bayesian optimization loop.

        Args:
            n_iterations: Total number of iterations
            checkpoint_interval: Save checkpoint every N iterations
            resume_from: Path to checkpoint file to resume from

        Returns:
            Dictionary with optimization results
        """
        if resume_from:
            self._load_checkpoint(resume_from)

        start_iter = len(self.results)
        logger.info(f"Starting optimization from iteration {start_iter}")

        for i in range(start_iter, n_iterations):
            logger.info(f"=== Iteration {i + 1}/{n_iterations} ===")

            # Select next point
            x_log = self._select_next_point()
            param_values = self._log_to_param_dict(x_log)

            logger.info(f"Selected parameters: {param_values}")

            # Run simulation
            run_id = f"opt_{i:03d}"
            h5_path, metadata = self.runner.run_simulation(
                param_values=param_values,
                run_id=run_id,
                keep_files=False
            )

            # Compute objective
            if h5_path is not None:
                obj_value = self.objective_func.compute(h5_path)
                logger.info(f"Objective value: {obj_value:.4f}")
            else:
                obj_value = self.objective_func.penalty_value
                logger.warning(f"Simulation failed, using penalty value: {obj_value}")

            # Update history
            self.X.append(x_log)
            self.y.append(obj_value)

            # Update GP surrogate
            if len(self.X) >= self.n_initial:
                X_array = np.array(self.X)
                y_array = np.array(self.y)
                self.gp.fit(X_array, y_array)

            # Track best
            is_best = obj_value < self.best_objective
            if is_best:
                self.best_objective = obj_value
                self.best_params = param_values.copy()
                logger.info(f"New best! Objective: {obj_value:.4f}")

            # Compute acquisition value for logging
            if len(self.X) >= self.n_initial:
                acq_value = float(self.expected_improvement(x_log.reshape(1, -1))[0])
            else:
                acq_value = np.nan

            # Store result
            result = OptimizationResult(
                iteration=i,
                param_values=param_values,
                param_values_log=dict(zip(self.param_names, x_log)),
                objective=obj_value,
                acquisition_value=acq_value,
                is_best=is_best,
                timestamp=datetime.now().isoformat()
            )
            self.results.append(result)

            # Checkpoint
            if (i + 1) % checkpoint_interval == 0:
                self._save_checkpoint()

        # Save final results
        self._save_checkpoint()
        return self._compile_results()

    def _compile_results(self) -> Dict[str, Any]:
        """Compile optimization results into summary dict."""
        return {
            'best_objective': self.best_objective,
            'best_params': self.best_params,
            'n_iterations': len(self.results),
            'convergence_history': [r.objective for r in self.results],
            'all_results': [r.to_dict() for r in self.results]
        }

    def _save_checkpoint(self):
        """Save optimization state to checkpoint file."""
        checkpoint = {
            'timestamp': datetime.now().isoformat(),
            'year': self.year,
            'meander': self.meander,
            'param_names': self.param_names,
            'bounds': self.bounds.tolist(),
            'n_initial': self.n_initial,
            'X': [x.tolist() for x in self.X],
            'y': self.y,
            'best_objective': self.best_objective,
            'best_params': self.best_params,
            'results': [r.to_dict() for r in self.results]
        }

        checkpoint_path = self.output_dir / 'checkpoint.json'
        with open(checkpoint_path, 'w') as f:
            json.dump(checkpoint, f, indent=2)

        # Also save results as CSV
        if self.results:
            df = pd.DataFrame([{
                'iteration': r.iteration,
                'objective': r.objective,
                'is_best': r.is_best,
                **r.param_values
            } for r in self.results])
            df.to_csv(self.output_dir / 'optimization_history.csv', index=False)

        logger.info(f"Saved checkpoint to {checkpoint_path}")

    def _load_checkpoint(self, checkpoint_path: Path):
        """Load optimization state from checkpoint."""
        with open(checkpoint_path) as f:
            checkpoint = json.load(f)

        self.param_names = checkpoint['param_names']
        self.n_params = len(self.param_names)
        self.bounds = np.array(checkpoint['bounds'])
        self.n_initial = checkpoint['n_initial']
        self.X = [np.array(x) for x in checkpoint['X']]
        self.y = checkpoint['y']
        self.best_objective = checkpoint['best_objective']
        self.best_params = checkpoint['best_params']
        self.results = [OptimizationResult(**r) for r in checkpoint['results']]

        # Rebuild GP with loaded data
        if len(self.X) >= self.n_initial:
            X_array = np.array(self.X)
            y_array = np.array(self.y)
            self.gp.fit(X_array, y_array)

        logger.info(f"Loaded checkpoint with {len(self.results)} iterations")

    def predict(self, param_values: Dict[str, float]) -> Tuple[float, float]:
        """
        Predict objective value for given parameters using GP surrogate.

        Args:
            param_values: Parameter dictionary

        Returns:
            Tuple of (mean prediction, standard deviation)
        """
        x_log = self._param_dict_to_log(param_values)
        mean, std = self.gp.predict(x_log.reshape(1, -1), return_std=True)
        return float(mean[0]), float(std[0])


def run_bayesian_optimization(year: str = '2019',
                              meander: str = 'mzt',
                              n_iterations: int = 50,
                              param_names: Optional[List[str]] = None,
                              output_dir: Optional[Path] = None,
                              **kwargs) -> Dict[str, Any]:
    """
    Convenience function to run Bayesian optimization.

    Args:
        year: Simulation year
        meander: Meander identifier
        n_iterations: Number of optimization iterations
        param_names: Parameters to optimize (None = all)
        output_dir: Output directory
        **kwargs: Additional arguments to BayesianOptimizer

    Returns:
        Dictionary with optimization results
    """
    optimizer = BayesianOptimizer(
        year=year,
        meander=meander,
        param_names=param_names,
        output_dir=output_dir,
        **kwargs
    )

    return optimizer.run_optimization(n_iterations)
