"""
PFLOTRAN Parameter Tuning Workflow

This package provides tools for tuning PFLOTRAN reactive transport model
parameters using sensitivity analysis and Bayesian optimization.

Modules:
    config: Parameter definitions, bounds, and configuration
    template_modifier: Parse and modify chemistry templates with $T markers
    simulation_runner: Run PFLOTRAN simulations with modified parameters
    objective: Compute weighted KGE objective function
    sensitivity: Morris method sensitivity analysis
    optimize: Bayesian optimization with Gaussian Process surrogate
    visualization: Diagnostic figures for tuning assessment
    main: CLI orchestration script

Usage:
    # From command line
    python -m tuning.main --phase sensitivity --meander mzt --year 2019

    # From Python
    from tuning.sensitivity import run_morris_analysis
    from tuning.optimize import run_bayesian_optimization
    from tuning.objective import compute_objective
    from tuning.visualization import TuningVisualizer

Example workflow:
    1. Run sensitivity analysis to identify influential parameters
    2. Run Bayesian optimization on the reduced parameter set
    3. Validate optimized parameters
"""

from .config import (
    Parameter,
    PARAMETERS,
    PARAM_BY_NAME,
    get_parameter_names,
    get_parameter_bounds,
    get_default_values,
    SIMULATION_CONFIGS,
    SPECIES_WEIGHTS,
)

from .template_modifier import (
    TemplateModifier,
    create_modified_template,
    validate_template,
)

from .simulation_runner import (
    SimulationRunner,
    run_single_simulation,
)

from .objective import (
    ObjectiveFunction,
    compute_objective,
    compute_objective_with_details,
)

from .sensitivity import (
    MorrisSensitivity,
    MorrisResult,
    run_morris_analysis,
)

from .optimize import (
    BayesianOptimizer,
    OptimizationResult,
    run_bayesian_optimization,
)

from .visualization import (
    TuningVisualizer,
    plot_one_to_one,
    plot_convergence,
    plot_residual_boxplots,
    generate_tuning_figures,
)

# Agentic workflow (requires anthropic package)
try:
    from .agent import (
        TuningAgent,
        run_agent_tuning,
    )
    _HAS_AGENT = True
except ImportError:
    _HAS_AGENT = False
    TuningAgent = None
    run_agent_tuning = None

__version__ = '0.1.0'
__author__ = 'Christian Dewey'

__all__ = [
    # Config
    'Parameter',
    'PARAMETERS',
    'PARAM_BY_NAME',
    'get_parameter_names',
    'get_parameter_bounds',
    'get_default_values',
    'SIMULATION_CONFIGS',
    'SPECIES_WEIGHTS',

    # Template modifier
    'TemplateModifier',
    'create_modified_template',
    'validate_template',

    # Simulation runner
    'SimulationRunner',
    'run_single_simulation',

    # Objective function
    'ObjectiveFunction',
    'compute_objective',
    'compute_objective_with_details',

    # Sensitivity analysis
    'MorrisSensitivity',
    'MorrisResult',
    'run_morris_analysis',

    # Optimization
    'BayesianOptimizer',
    'OptimizationResult',
    'run_bayesian_optimization',

    # Visualization
    'TuningVisualizer',
    'plot_one_to_one',
    'plot_convergence',
    'plot_residual_boxplots',
    'generate_tuning_figures',

    # Agentic workflow
    'TuningAgent',
    'run_agent_tuning',
]
