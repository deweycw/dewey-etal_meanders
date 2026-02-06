#!/usr/bin/env python3
"""
Main orchestration script for PFLOTRAN parameter tuning workflow.

This script provides a command-line interface for running:
1. Sensitivity analysis (Morris method)
2. Bayesian optimization
3. Validation of optimized parameters

Usage:
    python -m tuning.main --phase sensitivity --meander mzt --year 2019
    python -m tuning.main --phase optimize --meander mzt --year 2019 --n-iter 50
    python -m tuning.main --phase validate --meander mzt --year 2019 --params-file optimized_params.json
"""

import argparse
import logging
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

import numpy as np

from .config import (
    PARAMETERS, get_parameter_names, get_default_values,
    SIMULATION_CONFIGS, save_config
)
from .sensitivity import MorrisSensitivity, MorrisResult
from .optimize import BayesianOptimizer
from .simulation_runner import SimulationRunner
from .objective import ObjectiveFunction, compute_objective_with_details
from .template_modifier import validate_template

try:
    from .agent import TuningAgent, run_agent_tuning
    HAS_AGENT = True
except ImportError:
    HAS_AGENT = False

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('tuning.log')
    ]
)
logger = logging.getLogger(__name__)


def run_sensitivity(args: argparse.Namespace) -> List[MorrisResult]:
    """
    Run Morris sensitivity analysis.

    Args:
        args: Command line arguments

    Returns:
        List of MorrisResult objects
    """
    logger.info("="*60)
    logger.info("Starting Morris Sensitivity Analysis")
    logger.info("="*60)

    output_dir = Path(args.output_dir) if args.output_dir else \
                 Path(f'sensitivity_{args.meander}_{args.year}_{datetime.now():%Y%m%d_%H%M%S}')

    morris = MorrisSensitivity(
        year=args.year,
        meander=args.meander,
        n_trajectories=args.n_trajectories,
        n_levels=args.n_levels,
        seed=args.seed,
        output_dir=output_dir
    )

    # Resume from checkpoint if specified
    resume_from = Path(args.resume) if args.resume else None

    results = morris.run_analysis(
        checkpoint_interval=args.checkpoint_interval,
        resume_from=resume_from
    )

    # Print summary
    print("\n" + "="*60)
    print("MORRIS SENSITIVITY ANALYSIS RESULTS")
    print("="*60)
    print(f"\n{'Parameter':<40} {'μ*':>10} {'σ':>10} {'Rank':>6}")
    print("-"*70)

    for i, r in enumerate(results):
        print(f"{r.parameter_name:<40} {r.mu_star:>10.4f} {r.sigma:>10.4f} {i+1:>6}")

    # Identify influential parameters
    influential = morris.get_influential_parameters(threshold_quantile=0.5)
    print(f"\nInfluential parameters (μ* above median):")
    for p in influential:
        print(f"  - {p}")

    # Save influential parameters list
    with open(output_dir / 'influential_parameters.json', 'w') as f:
        json.dump(influential, f, indent=2)

    logger.info(f"Sensitivity analysis complete. Results saved to {output_dir}")

    return results


def run_optimize(args: argparse.Namespace) -> Dict[str, Any]:
    """
    Run Bayesian optimization.

    Args:
        args: Command line arguments

    Returns:
        Optimization results dictionary
    """
    logger.info("="*60)
    logger.info("Starting Bayesian Optimization")
    logger.info("="*60)

    output_dir = Path(args.output_dir) if args.output_dir else \
                 Path(f'optimize_{args.meander}_{args.year}_{datetime.now():%Y%m%d_%H%M%S}')

    # Determine which parameters to optimize
    if args.params_file:
        # Load influential parameters from sensitivity analysis
        with open(args.params_file) as f:
            param_names = json.load(f)
        logger.info(f"Optimizing {len(param_names)} parameters from {args.params_file}")
    else:
        param_names = get_parameter_names()
        logger.info(f"Optimizing all {len(param_names)} parameters")

    optimizer = BayesianOptimizer(
        year=args.year,
        meander=args.meander,
        param_names=param_names,
        n_initial=args.n_initial,
        output_dir=output_dir,
        seed=args.seed
    )

    # Resume from checkpoint if specified
    resume_from = Path(args.resume) if args.resume else None

    results = optimizer.run_optimization(
        n_iterations=args.n_iter,
        checkpoint_interval=args.checkpoint_interval,
        resume_from=resume_from
    )

    # Print summary
    print("\n" + "="*60)
    print("BAYESIAN OPTIMIZATION RESULTS")
    print("="*60)
    print(f"\nBest objective value: {results['best_objective']:.4f}")
    print("\nOptimized parameters:")
    for name, value in results['best_params'].items():
        print(f"  {name}: {value:.4e}")

    # Save optimized parameters
    with open(output_dir / 'optimized_params.json', 'w') as f:
        json.dump(results['best_params'], f, indent=2)

    logger.info(f"Optimization complete. Results saved to {output_dir}")

    return results


def run_validate(args: argparse.Namespace) -> Dict[str, Any]:
    """
    Run validation simulation with optimized parameters.

    Args:
        args: Command line arguments

    Returns:
        Validation results dictionary
    """
    logger.info("="*60)
    logger.info("Starting Validation Simulation")
    logger.info("="*60)

    # Load optimized parameters
    if args.params_file:
        with open(args.params_file) as f:
            param_values = json.load(f)
    else:
        raise ValueError("--params-file required for validation phase")

    output_dir = Path(args.output_dir) if args.output_dir else \
                 Path(f'validate_{args.meander}_{args.year}_{datetime.now():%Y%m%d_%H%M%S}')
    output_dir.mkdir(parents=True, exist_ok=True)

    # Run simulation
    runner = SimulationRunner(year=args.year, meander=args.meander)

    logger.info("Running simulation with optimized parameters...")
    h5_path, metadata = runner.run_simulation(
        param_values=param_values,
        run_id='validation',
        keep_files=True
    )

    if h5_path is None:
        logger.error("Validation simulation failed!")
        return {'status': 'failed', 'error': metadata.get('error')}

    # Compute detailed objective
    logger.info("Computing validation metrics...")
    results = compute_objective_with_details(
        h5_path,
        year=args.year,
        meander=args.meander
    )

    # Print validation results
    print("\n" + "="*60)
    print("VALIDATION RESULTS")
    print("="*60)
    print(f"\nOverall objective: {results['objective']:.4f}")
    print(f"\nPer-species metrics:")
    print(f"{'Species':<10} {'KGE':>8} {'NSE':>8} {'RMSE':>10} {'n_obs':>6}")
    print("-"*50)

    for species, metrics in results['species_metrics'].items():
        kge = metrics['KGE']
        nse = metrics.get('NSE', np.nan)
        rmse = metrics.get('RMSE', np.nan)
        n_obs = metrics['n_obs']
        print(f"{species:<10} {kge:>8.3f} {nse:>8.3f} {rmse:>10.4f} {n_obs:>6}")

    # Save validation results
    validation_results = {
        'objective': results['objective'],
        'h5_path': str(h5_path),
        'param_values': param_values,
        'species_metrics': results['species_metrics'],
        'simulation_metadata': metadata
    }

    with open(output_dir / 'validation_results.json', 'w') as f:
        json.dump(validation_results, f, indent=2, default=str)

    logger.info(f"Validation complete. Results saved to {output_dir}")

    return validation_results


def run_template_check(args: argparse.Namespace):
    """Validate the chemistry template has correct $T markers."""
    template_path = Path(args.template or
                         '/home/christiandewey/Code/dewey-etal_meanders/pflotran/simulations/TEMPLATE-chemistry.txt')

    is_valid, issues = validate_template(template_path)

    print("\n" + "="*60)
    print("TEMPLATE VALIDATION")
    print("="*60)
    print(f"\nTemplate: {template_path}")
    print(f"Valid: {is_valid}")

    if issues:
        print("\nIssues found:")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("\nNo issues found. Template is ready for tuning.")


def run_agent(args: argparse.Namespace) -> Dict[str, Any]:
    """
    Run agentic AI tuning workflow.

    This uses Claude to intelligently reason about results and
    make parameter adjustments based on biogeochemical understanding.

    Args:
        args: Command line arguments

    Returns:
        Results dictionary
    """
    if not HAS_AGENT:
        print("Error: anthropic package required for agent mode.")
        print("Install with: pip install anthropic")
        sys.exit(1)

    logger.info("="*60)
    logger.info("Starting Agentic AI Tuning Workflow")
    logger.info("="*60)

    output_dir = Path(args.output_dir) if args.output_dir else \
                 Path(f'agent_{args.meander}_{args.year}_{datetime.now():%Y%m%d_%H%M%S}')

    # Load initial parameters if specified
    initial_params = None
    if args.params_file:
        with open(args.params_file) as f:
            initial_params = json.load(f)

    agent = TuningAgent(
        year=args.year,
        meander=args.meander,
        max_iterations=args.n_iter,
        output_dir=output_dir,
        api_key=args.api_key,
        skip_spin=args.skip_spin
    )

    results = agent.run(
        initial_params=initial_params,
        resume=args.resume is not None
    )

    # Print summary
    print("\n" + "="*60)
    print("AGENTIC TUNING RESULTS")
    print("="*60)
    print(f"\nBest objective value: {results['best_objective']:.4f}")
    print(f"Iterations completed: {results['n_iterations']}")
    print("\nKey insights discovered:")
    for insight in results['insights'][-5:]:
        print(f"  - {insight}")

    print("\nOptimized parameters saved to:")
    print(f"  {output_dir / 'best_params.json'}")

    return results


def main():
    """Main entry point for the tuning workflow."""
    parser = argparse.ArgumentParser(
        description='PFLOTRAN Parameter Tuning Workflow',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run sensitivity analysis
  python -m tuning.main --phase sensitivity --meander mzt --year 2019 --n-trajectories 10

  # Run optimization with influential parameters
  python -m tuning.main --phase optimize --meander mzt --year 2019 \\
      --params-file sensitivity_mzt_2019/influential_parameters.json --n-iter 50

  # Validate optimized parameters
  python -m tuning.main --phase validate --meander mzt --year 2019 \\
      --params-file optimize_mzt_2019/optimized_params.json

  # Check template markers
  python -m tuning.main --phase check-template
        """
    )

    parser.add_argument('--phase', required=True,
                        choices=['sensitivity', 'optimize', 'validate', 'check-template', 'agent'],
                        help='Phase of the workflow to run')
    parser.add_argument('--meander', choices=['mzt', 'mcp'], default='mzt',
                        help='Meander identifier')
    parser.add_argument('--year', choices=['2018', '2019'], default='2019',
                        help='Simulation year')
    parser.add_argument('--output-dir', help='Output directory for results')
    parser.add_argument('--seed', type=int, help='Random seed for reproducibility')
    parser.add_argument('--resume', help='Path to checkpoint file to resume from')
    parser.add_argument('--checkpoint-interval', type=int, default=5,
                        help='Save checkpoint every N simulations')

    # Sensitivity-specific arguments
    parser.add_argument('--n-trajectories', type=int, default=10,
                        help='Number of Morris trajectories')
    parser.add_argument('--n-levels', type=int, default=4,
                        help='Number of grid levels for Morris method')

    # Optimization-specific arguments
    parser.add_argument('--n-iter', type=int, default=50,
                        help='Number of optimization iterations')
    parser.add_argument('--n-initial', type=int, default=5,
                        help='Number of initial random samples')
    parser.add_argument('--params-file',
                        help='JSON file with parameter names (for optimize) or values (for validate)')

    # Template check arguments
    parser.add_argument('--template', help='Path to chemistry template file')

    # Agent-specific arguments
    parser.add_argument('--api-key', help='Anthropic API key (or set ANTHROPIC_API_KEY)')
    parser.add_argument('--skip-spin', action='store_true',
                        help='Skip spin simulations by using a reference checkpoint. '
                             'Generates checkpoint automatically if needed. '
                             'Speeds up iterations from ~1-2 hours to ~20-30 minutes.')

    args = parser.parse_args()

    # Route to appropriate function
    if args.phase == 'sensitivity':
        run_sensitivity(args)
    elif args.phase == 'optimize':
        run_optimize(args)
    elif args.phase == 'validate':
        run_validate(args)
    elif args.phase == 'check-template':
        run_template_check(args)
    elif args.phase == 'agent':
        run_agent(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()
