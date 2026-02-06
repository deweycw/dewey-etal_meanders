"""
Parameter configuration for PFLOTRAN tuning workflow.

This module loads tunable parameters from tuning_config.yaml and provides
helper functions for parameter manipulation.
"""

import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from pathlib import Path
import yaml
import numpy as np


# Path to the configuration file
CONFIG_FILE = Path(__file__).parent / "tuning_config.yaml"


@dataclass
class Parameter:
    """Configuration for a single tunable parameter."""
    name: str
    block: str  # The reaction block this parameter belongs to
    keyword: str  # The PFLOTRAN keyword (e.g., RATE_CONSTANT, RMAX)
    default: float  # Default value
    bounds: Tuple[float, float]  # (lower, upper) bounds
    is_log_scale: bool = True  # Whether to optimize in log space
    description: str = ""

    @property
    def log_bounds(self) -> Tuple[float, float]:
        """Return bounds in log10 space."""
        if self.is_log_scale:
            return (np.log10(self.bounds[0]), np.log10(self.bounds[1]))
        return self.bounds

    @property
    def log_default(self) -> float:
        """Return default value in log10 space."""
        if self.is_log_scale:
            return np.log10(self.default)
        return self.default


def _load_yaml_config(filepath: Optional[Path] = None) -> dict:
    """Load the full configuration from YAML file."""
    if filepath is None:
        filepath = CONFIG_FILE
    with open(filepath) as f:
        return yaml.safe_load(f)


def _parse_parameters_from_yaml(config: dict) -> List[Parameter]:
    """Parse parameter definitions from YAML config dict."""
    params = []
    for pconfig in config.get('parameters', []):
        params.append(Parameter(
            name=pconfig['name'],
            block=pconfig['block'],
            keyword=pconfig['keyword'],
            default=pconfig['default'],
            bounds=tuple(pconfig['bounds']),
            is_log_scale=pconfig.get('is_log_scale', True),
            description=pconfig.get('description', '')
        ))
    return params


def reload_config(filepath: Optional[Path] = None):
    """
    Reload configuration from YAML file.

    Call this if you modify tuning_config.yaml and want to pick up changes
    without restarting Python.
    """
    global PARAMETERS, PARAM_BY_NAME, SPECIES_WEIGHTS, _CONFIG

    _CONFIG = _load_yaml_config(filepath)
    PARAMETERS = _parse_parameters_from_yaml(_CONFIG)

    # Rebuild lookup dictionary
    PARAM_BY_NAME = {p.name: p for p in PARAMETERS}

    # Add porosity parameters to lookup
    for p in POROSITY_PARAMETERS:
        PARAM_BY_NAME[p.name] = p

    # Update species weights from YAML
    if 'objective' in _CONFIG and 'species_weights' in _CONFIG['objective']:
        SPECIES_WEIGHTS.update(_CONFIG['objective']['species_weights'])


# Load configuration on module import
_CONFIG = _load_yaml_config()

# Parse parameters from YAML
PARAMETERS: List[Parameter] = _parse_parameters_from_yaml(_CONFIG)

# Create lookup dictionary by parameter name
PARAM_BY_NAME: Dict[str, Parameter] = {p.name: p for p in PARAMETERS}

# Simulation configurations for different meander/year combinations
SIMULATION_CONFIGS = {
    ('2019', 'mzt'): {
        'nx': 108,
        'subdir': 'mzt19',
        'startdate': '2019-04-19',
        'final_time_hours': 3993,
    },
    ('2019', 'mcp'): {
        'nx': 122,
        'subdir': 'mcp19',
        'startdate': '2019-04-19',
        'final_time_hours': 3993,
    },
    ('2018', 'mzt'): {
        'nx': 108,
        'subdir': 'mzt18',
        'startdate': '2018-05-01',
        'final_time_hours': 5131,
    },
    ('2018', 'mcp'): {
        'nx': 122,
        'subdir': 'mcp18',
        'startdate': '2018-05-01',
        'final_time_hours': 5131,
    },
}

# Objective function weights for each species (loaded from YAML, with defaults)
SPECIES_WEIGHTS = {
    'TIC': 1.0,
    'pH': 1.0,
    'Ca': 0.8,
    'Mg': 0.8,
    'Fe': 0.8,
    'SO4': 0.7,
    'NPOC': 0.6,
    'NO3': 0.3,
    'DO': 0.3,
}
# Override with YAML values
if 'objective' in _CONFIG and 'species_weights' in _CONFIG['objective']:
    SPECIES_WEIGHTS.update(_CONFIG['objective']['species_weights'])

# Meander-specific species lists for tuning
MEANDER_SPECIES = {
    'mzt': ['TIC', 'pH', 'Ca', 'Mg', 'DO'],
    'mcp': ['TIC', 'pH', 'Ca', 'Fe', 'SO4', 'NPOC', 'NO3', 'DO'],
}

# Meander-specific parameter lists for tuning
MEANDER_PARAMETERS = {
    'mzt': [
        'root_respiration_dissolution_rate',
        'aerobic_rate_constant',
        'aerobic_o2_half_sat',
        'aerobic_soc_half_sat',
    ],
    'mcp': None,  # Use all parameters for MCP
}

# Porosity parameters (in main PFLOTRAN template, not chemistry template)
# Disabled - porosity tuning is currently turned off
POROSITY_PARAMETERS: List[Parameter] = []

# Add porosity parameters to lookup
for p in POROSITY_PARAMETERS:
    PARAM_BY_NAME[p.name] = p


def get_config() -> dict:
    """Return the full configuration dictionary."""
    return _CONFIG


def get_simulation_config() -> dict:
    """Return simulation settings from YAML."""
    return _CONFIG.get('simulation', {})


def get_objective_config() -> dict:
    """Return objective function settings from YAML."""
    return _CONFIG.get('objective', {})


def get_sensitivity_config() -> dict:
    """Return sensitivity analysis settings from YAML."""
    return _CONFIG.get('sensitivity', {})


def get_optimization_config() -> dict:
    """Return optimization settings from YAML."""
    return _CONFIG.get('optimization', {})


def get_species_for_meander(meander: str) -> List[str]:
    """
    Get the list of species to use for tuning a specific meander.

    Args:
        meander: Meander identifier (e.g., 'mzt', 'mcp')

    Returns:
        List of species names to use for objective function
    """
    meander_lower = meander.lower()
    if meander_lower in MEANDER_SPECIES:
        return MEANDER_SPECIES[meander_lower]
    return list(SPECIES_WEIGHTS.keys())


def get_parameters_for_meander(meander: str) -> List[str]:
    """
    Get the list of parameters to tune for a specific meander.

    Args:
        meander: Meander identifier (e.g., 'mzt', 'mcp')

    Returns:
        List of parameter names to tune
    """
    meander_lower = meander.lower()
    if meander_lower in MEANDER_PARAMETERS and MEANDER_PARAMETERS[meander_lower] is not None:
        return MEANDER_PARAMETERS[meander_lower]
    return get_parameter_names()


def get_parameter_names() -> List[str]:
    """Return list of all parameter names."""
    return [p.name for p in PARAMETERS]


def get_parameter_bounds(param_names: Optional[List[str]] = None,
                          log_scale: bool = True) -> np.ndarray:
    """
    Return bounds array for specified parameters.

    Args:
        param_names: List of parameter names. If None, uses all parameters.
        log_scale: If True, return bounds in log10 space.

    Returns:
        Array of shape (n_params, 2) with [lower, upper] bounds.
    """
    if param_names is None:
        param_names = get_parameter_names()

    bounds = []
    for name in param_names:
        p = PARAM_BY_NAME[name]
        if log_scale and p.is_log_scale:
            bounds.append(p.log_bounds)
        else:
            bounds.append(p.bounds)

    return np.array(bounds)


def get_default_values(param_names: Optional[List[str]] = None,
                        log_scale: bool = True) -> np.ndarray:
    """
    Return default values for specified parameters.

    Args:
        param_names: List of parameter names. If None, uses all parameters.
        log_scale: If True, return values in log10 space.

    Returns:
        Array of default values.
    """
    if param_names is None:
        param_names = get_parameter_names()

    defaults = []
    for name in param_names:
        p = PARAM_BY_NAME[name]
        if log_scale and p.is_log_scale:
            defaults.append(p.log_default)
        else:
            defaults.append(p.default)

    return np.array(defaults)


def transform_to_linear(values: np.ndarray,
                        param_names: List[str]) -> np.ndarray:
    """
    Transform values from log10 space to linear space.

    Args:
        values: Array of values (potentially in log10 space)
        param_names: Corresponding parameter names

    Returns:
        Array of values in linear space.
    """
    result = np.zeros_like(values)
    for i, name in enumerate(param_names):
        p = PARAM_BY_NAME[name]
        if p.is_log_scale:
            result[i] = 10 ** values[i]
        else:
            result[i] = values[i]
    return result


def transform_to_log(values: np.ndarray,
                     param_names: List[str]) -> np.ndarray:
    """
    Transform values from linear space to log10 space.

    Args:
        values: Array of values in linear space
        param_names: Corresponding parameter names

    Returns:
        Array of values in log10 space (where applicable).
    """
    result = np.zeros_like(values)
    for i, name in enumerate(param_names):
        p = PARAM_BY_NAME[name]
        if p.is_log_scale:
            result[i] = np.log10(values[i])
        else:
            result[i] = values[i]
    return result


def save_config(filepath: Path, param_names: Optional[List[str]] = None):
    """Save parameter configuration to YAML file."""
    if param_names is None:
        param_names = get_parameter_names()

    config = {
        'parameters': []
    }

    for name in param_names:
        p = PARAM_BY_NAME[name]
        config['parameters'].append({
            'name': p.name,
            'block': p.block,
            'keyword': p.keyword,
            'default': float(p.default),
            'bounds': [float(p.bounds[0]), float(p.bounds[1])],
            'is_log_scale': p.is_log_scale,
            'description': p.description
        })

    with open(filepath, 'w') as f:
        yaml.dump(config, f, default_flow_style=False)


def load_config(filepath: Path) -> List[Parameter]:
    """Load parameter configuration from YAML file."""
    with open(filepath) as f:
        config = yaml.safe_load(f)

    params = []
    for pconfig in config['parameters']:
        params.append(Parameter(
            name=pconfig['name'],
            block=pconfig['block'],
            keyword=pconfig['keyword'],
            default=pconfig['default'],
            bounds=tuple(pconfig['bounds']),
            is_log_scale=pconfig.get('is_log_scale', True),
            description=pconfig.get('description', '')
        ))

    return params
