"""
Visualization module for PFLOTRAN parameter tuning results.

Generates diagnostic figures for tuning assessment:
- 1:1 plots with RMSE and R²
- Concentration vs. date time series with observations and model output
- Residuals vs. time (error analysis)
- Objective function convergence (performance metric)
- Box plots of residuals by species (distribution comparison)
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime

import numpy as np
import pandas as pd
import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.figure import Figure

logger = logging.getLogger(__name__)

# Use non-interactive backend for server/CLI usage
mpl.use('Agg')


def setup_style():
    """Configure matplotlib style for publication-quality figures."""
    mpl.rcParams['mathtext.default'] = 'rm'
    mpl.rcParams['legend.fontsize'] = 8
    mpl.rcParams['axes.labelsize'] = 10
    mpl.rcParams['axes.titlesize'] = 11
    mpl.rcParams['xtick.labelsize'] = 9
    mpl.rcParams['ytick.labelsize'] = 9
    mpl.rcParams['figure.dpi'] = 150


def get_viridis_colors(n: int = 5) -> List:
    """Get evenly spaced colors from viridis colormap."""
    cmap = mpl.cm.get_cmap('viridis')
    return [cmap(i) for i in np.linspace(0, 0.9, n)]


def plot_one_to_one(observed: np.ndarray,
                    simulated: np.ndarray,
                    species_name: str,
                    ax: Optional[plt.Axes] = None,
                    unit: str = '') -> Tuple[plt.Axes, Dict[str, float]]:
    """
    Create a 1:1 plot comparing observed vs simulated values.

    Args:
        observed: Array of observed values
        simulated: Array of simulated values
        species_name: Name of the species for labeling
        ax: Optional matplotlib axes to plot on
        unit: Unit string for axis labels

    Returns:
        Tuple of (axes, metrics_dict) where metrics_dict contains RMSE and R²
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=(5, 5))

    # Calculate metrics
    rmse = np.sqrt(np.mean((simulated - observed) ** 2))

    # R² calculation
    ss_res = np.sum((observed - simulated) ** 2)
    ss_tot = np.sum((observed - np.mean(observed)) ** 2)
    r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else np.nan

    # Pearson correlation
    if len(observed) > 1 and np.std(observed) > 0 and np.std(simulated) > 0:
        r = np.corrcoef(observed, simulated)[0, 1]
    else:
        r = np.nan

    # Plot data points
    ax.scatter(observed, simulated, alpha=0.6, edgecolors='k', linewidth=0.5, s=40)

    # Plot 1:1 line
    all_vals = np.concatenate([observed, simulated])
    min_val, max_val = np.min(all_vals), np.max(all_vals)
    margin = (max_val - min_val) * 0.1
    line_range = [min_val - margin, max_val + margin]
    ax.plot(line_range, line_range, 'k--', linewidth=1, label='1:1 line')

    # Set equal aspect and limits
    ax.set_xlim(line_range)
    ax.set_ylim(line_range)
    ax.set_aspect('equal')

    # Labels
    unit_str = f' ({unit})' if unit else ''
    ax.set_xlabel(f'Observed{unit_str}')
    ax.set_ylabel(f'Simulated{unit_str}')
    ax.set_title(species_name)

    # Add metrics text box
    textstr = f'RMSE = {rmse:.3g}\nR² = {r2:.3f}\nn = {len(observed)}'
    props = dict(boxstyle='round', facecolor='white', alpha=0.8)
    ax.text(0.05, 0.95, textstr, transform=ax.transAxes, fontsize=9,
            verticalalignment='top', bbox=props)

    ax.grid(True, alpha=0.3)

    metrics = {'rmse': rmse, 'r2': r2, 'r': r, 'n': len(observed)}
    return ax, metrics


def plot_time_series_comparison(sim_times: np.ndarray,
                                 sim_values: np.ndarray,
                                 obs_dates: np.ndarray,
                                 obs_values: np.ndarray,
                                 species_name: str,
                                 startdate: np.datetime64,
                                 ax: Optional[plt.Axes] = None,
                                 unit: str = '',
                                 location_label: str = '') -> plt.Axes:
    """
    Plot concentration vs. date with observations and model output.

    Args:
        sim_times: Simulation times in hours from startdate
        sim_values: Simulated concentration values
        obs_dates: Observation datetime values
        obs_values: Observed concentration values
        species_name: Name of the species for labeling
        startdate: Simulation start date
        ax: Optional matplotlib axes
        unit: Unit string for y-axis label
        location_label: Optional location identifier for legend

    Returns:
        matplotlib axes
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=(8, 4))

    # Convert simulation times to datetime
    sim_dates = [startdate + np.timedelta64(int(t), 'h') for t in sim_times]

    # Plot simulation
    label_sim = f'Model{" " + location_label if location_label else ""}'
    ax.plot(sim_dates, sim_values, '-', linewidth=1.5, label=label_sim, alpha=0.8)

    # Plot observations
    label_obs = f'Observed{" " + location_label if location_label else ""}'
    ax.scatter(obs_dates, obs_values, marker='o', s=30, edgecolors='k',
               linewidth=0.5, label=label_obs, zorder=5)

    # Formatting
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%-d-%b"))
    ax.set_xlabel('Date')
    unit_str = f' ({unit})' if unit else ''
    ax.set_ylabel(f'{species_name}{unit_str}')
    ax.legend(loc='best', fontsize=8)
    ax.grid(True, alpha=0.3)

    return ax


def plot_residuals_vs_time(obs_dates: np.ndarray,
                           residuals: np.ndarray,
                           species_name: str,
                           ax: Optional[plt.Axes] = None,
                           unit: str = '') -> plt.Axes:
    """
    Plot residuals (simulated - observed) vs. time.

    Args:
        obs_dates: Observation datetime values
        residuals: Residual values (simulated - observed)
        species_name: Name of the species for labeling
        ax: Optional matplotlib axes
        unit: Unit string for y-axis label

    Returns:
        matplotlib axes
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=(8, 4))

    # Plot residuals
    ax.scatter(obs_dates, residuals, alpha=0.6, edgecolors='k', linewidth=0.5, s=40)

    # Add zero line
    ax.axhline(y=0, color='k', linestyle='--', linewidth=1)

    # Add mean residual line
    mean_resid = np.mean(residuals)
    ax.axhline(y=mean_resid, color='r', linestyle=':', linewidth=1,
               label=f'Mean = {mean_resid:.3g}')

    # Formatting
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%-d-%b"))
    ax.set_xlabel('Date')
    unit_str = f' ({unit})' if unit else ''
    ax.set_ylabel(f'Residual{unit_str}')
    ax.set_title(f'{species_name} Residuals vs. Time')
    ax.legend(loc='best', fontsize=8)
    ax.grid(True, alpha=0.3)

    return ax


def plot_convergence(history: List[Dict[str, Any]],
                     ax: Optional[plt.Axes] = None) -> plt.Axes:
    """
    Plot objective function convergence over iterations.

    Args:
        history: List of iteration history dictionaries with 'objective' key
        ax: Optional matplotlib axes

    Returns:
        matplotlib axes
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=(8, 5))

    iterations = [h['iteration'] for h in history]
    objectives = [h['objective'] for h in history]

    # Plot objective values
    ax.plot(iterations, objectives, 'o-', markersize=6, linewidth=1.5,
            color='steelblue', label='Objective')

    # Plot running minimum
    running_min = np.minimum.accumulate(objectives)
    ax.plot(iterations, running_min, '--', linewidth=2, color='darkred',
            label='Best so far')

    # Formatting
    ax.set_xlabel('Iteration')
    ax.set_ylabel('Objective (1 - KGE)')
    ax.set_title('Objective Function Convergence')
    ax.legend(loc='best')
    ax.grid(True, alpha=0.3)

    # Set y-axis to start from 0 if all values are positive
    if min(objectives) >= 0:
        ax.set_ylim(bottom=0)

    return ax


def plot_residual_boxplots(species_residuals: Dict[str, np.ndarray],
                           ax: Optional[plt.Axes] = None) -> plt.Axes:
    """
    Create box plots of residuals by species.

    Args:
        species_residuals: Dictionary mapping species names to residual arrays
        ax: Optional matplotlib axes

    Returns:
        matplotlib axes
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=(10, 5))

    # Prepare data for boxplot
    species_names = list(species_residuals.keys())
    data = [species_residuals[s] for s in species_names]

    # Create boxplot
    bp = ax.boxplot(data, labels=species_names, patch_artist=True)

    # Color the boxes
    colors = get_viridis_colors(len(species_names))
    for patch, color in zip(bp['boxes'], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)

    # Add zero line
    ax.axhline(y=0, color='k', linestyle='--', linewidth=1)

    # Formatting
    ax.set_xlabel('Species')
    ax.set_ylabel('Residual (Simulated - Observed)')
    ax.set_title('Residual Distribution by Species')
    ax.grid(True, alpha=0.3, axis='y')

    # Rotate x labels if many species
    if len(species_names) > 5:
        plt.setp(ax.get_xticklabels(), rotation=45, ha='right')

    return ax


class TuningVisualizer:
    """
    Generates visualization figures for tuning results.

    Creates a comprehensive set of diagnostic plots for each simulation
    to assess model performance.
    """

    # Species to include in time series and 1:1 plots
    PLOT_SPECIES = ['TIC', 'Fe', 'SO4', 'Ca', 'pH']

    # Whether to normalize residuals for cross-species comparison
    NORMALIZE_RESIDUALS = True

    def __init__(self,
                 year: str,
                 meander: str,
                 output_dir: Path,
                 startdate: np.datetime64):
        """
        Initialize the visualizer.

        Args:
            year: Simulation year
            meander: Meander identifier
            output_dir: Directory to save figures
            startdate: Simulation start date
        """
        self.year = year
        self.meander = meander
        self.output_dir = Path(output_dir)
        self.startdate = startdate
        self.figures_dir = self.output_dir / 'figures'
        self.figures_dir.mkdir(parents=True, exist_ok=True)

        setup_style()

    def generate_iteration_figures(self,
                                    iteration: int,
                                    kge_results: Dict[str, Any],
                                    objective: float,
                                    processor: Optional[Any] = None,
                                    chem_obs: Optional[Any] = None) -> List[Path]:
        """
        Generate all diagnostic figures for a single iteration.

        Args:
            iteration: Iteration number
            kge_results: Dictionary with KGE results including observed/simulated arrays
            objective: Objective function value
            processor: Optional PflotranProcessor for concentration history plots
            chem_obs: Optional observations DataFrame for history plots

        Returns:
            List of paths to generated figure files
        """
        generated_files = []

        # Create iteration subdirectory
        iter_dir = self.figures_dir / f'iter_{iteration:03d}'
        iter_dir.mkdir(exist_ok=True)

        # Extract component results
        component_results = {}
        if 'summary' in kge_results:
            # Full KGE results from processor
            for comp_name, comp_data in kge_results.items():
                if isinstance(comp_data, dict) and 'observed' in comp_data:
                    component_results[comp_data.get('obs_component', comp_name)] = comp_data
        elif 'species_metrics' in kge_results:
            # Results from objective function
            component_results = kge_results.get('component_results', {})

        # Filter to plot species (TIC, Fe, SO4, Ca, pH)
        filtered_results = self._filter_to_plot_species(component_results)

        if not filtered_results:
            logger.warning(f"No species matched PLOT_SPECIES filter. Available: {list(component_results.keys())}")
            return generated_files

        # 1. Generate 1:1 validation plots
        if processor is not None and chem_obs is not None:
            try:
                validation_path = self.plot_validation_panels(
                    processor=processor,
                    chem_obs=chem_obs,
                    output_dir=iter_dir,
                    label=iteration
                )
                if validation_path:
                    generated_files.append(validation_path)
                    logger.info(f"Saved validation 1:1 plots: {validation_path}")
            except Exception as e:
                logger.error(f"Failed to generate validation plots: {e}")
        else:
            # Fallback to simple 1:1 plots if no processor available
            try:
                one_to_one_path = self._plot_all_one_to_one(filtered_results, iter_dir, iteration)
                if one_to_one_path:
                    generated_files.append(one_to_one_path)
                    logger.info(f"Saved 1:1 plot: {one_to_one_path}")
            except Exception as e:
                logger.error(f"Failed to generate 1:1 plot: {e}")

        # 2. Generate concentration history plots (sim vs obs over time)
        if processor is not None and chem_obs is not None:
            try:
                history_path = self.plot_concentration_histories(
                    processor=processor,
                    chem_obs=chem_obs,
                    output_dir=iter_dir,
                    label=iteration
                )
                if history_path:
                    generated_files.append(history_path)
                    logger.info(f"Saved concentration histories: {history_path}")
            except Exception as e:
                logger.error(f"Failed to generate concentration histories: {e}")
        else:
            # Fallback to simple time series if no processor available
            try:
                timeseries_path = self._plot_all_time_series(filtered_results, iter_dir, iteration)
                if timeseries_path:
                    generated_files.append(timeseries_path)
                    logger.info(f"Saved time series plot: {timeseries_path}")
            except Exception as e:
                logger.error(f"Failed to generate time series plot: {e}")

        # 4. Generate residual boxplots
        try:
            boxplot_path = self._plot_residual_boxplots(filtered_results, iter_dir, iteration)
            if boxplot_path:
                generated_files.append(boxplot_path)
                logger.info(f"Saved boxplot: {boxplot_path}")
        except Exception as e:
            logger.error(f"Failed to generate boxplot: {e}")

        logger.info(f"Generated {len(generated_files)} figures for iteration {iteration} in {iter_dir}")
        return generated_files

    def _filter_to_plot_species(self, component_results: Dict[str, Dict]) -> Dict[str, Dict]:
        """Filter component results to only include PLOT_SPECIES (TIC, Fe, SO4, Ca, pH)."""
        filtered = {}
        for species_name, data in component_results.items():
            # Check if this species matches any of our plot species
            for plot_species in self.PLOT_SPECIES:
                if plot_species.lower() in species_name.lower() or species_name.lower() in plot_species.lower():
                    filtered[species_name] = data
                    break
        logger.info(f"Filtered {len(component_results)} species to {len(filtered)} plot species: {list(filtered.keys())}")
        return filtered

    def _plot_all_time_series(self,
                               component_results: Dict[str, Dict],
                               output_dir: Path,
                               label: Any) -> Optional[Path]:
        """Generate time series comparison plots for key species."""
        if not component_results:
            return None

        # Filter to components with temporal data
        valid_components = {k: v for k, v in component_results.items()
                           if 'observed' in v and 'simulated' in v and len(v['observed']) > 0}

        if not valid_components:
            return None

        n_species = len(valid_components)
        n_cols = min(2, n_species)
        n_rows = int(np.ceil(n_species / n_cols))

        fig, axes = plt.subplots(n_rows, n_cols, figsize=(7*n_cols, 4*n_rows))
        if n_species == 1:
            axes = np.array([axes])
        axes = axes.flatten()

        for idx, (species_name, data) in enumerate(valid_components.items()):
            obs = np.array(data['observed'])
            sim = np.array(data['simulated'])

            ax = axes[idx]

            # Get observation dates if available, otherwise use indices
            if 'obs_dates' in data:
                obs_dates = data['obs_dates']
                sim_dates = data.get('sim_dates', obs_dates)

                ax.plot(sim_dates, sim, '-', linewidth=1.5, color='steelblue',
                       label='Simulated', alpha=0.8)
                ax.scatter(obs_dates, obs, marker='o', s=40, color='darkorange',
                          edgecolors='k', linewidth=0.5, label='Observed', zorder=5)
                ax.xaxis.set_major_formatter(mdates.DateFormatter("%-d-%b"))
                ax.set_xlabel('Date')
            else:
                # Use observation index
                x = np.arange(len(obs))
                ax.plot(x, sim, '-', linewidth=1.5, color='steelblue',
                       label='Simulated', alpha=0.8)
                ax.scatter(x, obs, marker='o', s=40, color='darkorange',
                          edgecolors='k', linewidth=0.5, label='Observed', zorder=5)
                ax.set_xlabel('Observation Index')

            ax.set_ylabel(species_name)
            ax.set_title(species_name)
            ax.legend(loc='best', fontsize=8)
            ax.grid(True, alpha=0.3)

        # Hide unused axes
        for idx in range(len(valid_components), len(axes)):
            axes[idx].set_visible(False)

        fig.suptitle(f'Simulated vs Observed Concentrations - Iteration {label}',
                    fontsize=12, fontweight='bold')
        plt.tight_layout()

        filepath = output_dir / f'timeseries_{label}.png'
        fig.savefig(filepath, dpi=150, bbox_inches='tight')
        plt.close(fig)

        return filepath

    def generate_summary_figures(self,
                                  history: List[Dict[str, Any]],
                                  best_kge_results: Optional[Dict[str, Any]] = None,
                                  processor: Optional[Any] = None,
                                  chem_obs: Optional[Any] = None) -> List[Path]:
        """
        Generate summary figures for the complete tuning run.

        Args:
            history: List of iteration history dictionaries
            best_kge_results: Optional KGE results for the best iteration
            processor: Optional PflotranProcessor for best iteration plots
            chem_obs: Optional observations DataFrame for best iteration plots

        Returns:
            List of paths to generated figure files
        """
        generated_files = []

        # 1. Convergence plot
        convergence_path = self._plot_convergence(history)
        if convergence_path:
            generated_files.append(convergence_path)

        # 2. Per-species KGE evolution
        species_evolution_path = self._plot_species_kge_evolution(history)
        if species_evolution_path:
            generated_files.append(species_evolution_path)

        # 3. Best iteration validation and history plots using processor
        if processor is not None and chem_obs is not None:
            # Validation 1:1 plots for best iteration
            try:
                validation_path = self.plot_validation_panels(
                    processor=processor,
                    chem_obs=chem_obs,
                    output_dir=self.figures_dir,
                    label='best'
                )
                if validation_path:
                    generated_files.append(validation_path)
            except Exception as e:
                logger.error(f"Failed to generate best validation plots: {e}")

            # Concentration histories for best iteration
            try:
                history_path = self.plot_concentration_histories(
                    processor=processor,
                    chem_obs=chem_obs,
                    output_dir=self.figures_dir,
                    label='best'
                )
                if history_path:
                    generated_files.append(history_path)
            except Exception as e:
                logger.error(f"Failed to generate best concentration histories: {e}")

        elif best_kge_results:
            # Fallback to simple plots if no processor available
            component_results = {}
            components_dict = best_kge_results.get('components', {})
            for comp_name, comp_data in components_dict.items():
                if isinstance(comp_data, dict) and 'observed' in comp_data:
                    component_results[comp_data.get('obs_component', comp_name)] = comp_data

            filtered_results = self._filter_to_plot_species(component_results)

            if filtered_results:
                best_one_to_one_path = self._plot_all_one_to_one(
                    filtered_results, self.figures_dir, 'best'
                )
                if best_one_to_one_path:
                    generated_files.append(best_one_to_one_path)

                best_timeseries_path = self._plot_all_time_series(
                    filtered_results, self.figures_dir, 'best'
                )
                if best_timeseries_path:
                    generated_files.append(best_timeseries_path)

        # 4. Residual boxplots for best iteration
        if best_kge_results:
            component_results = {}
            components_dict = best_kge_results.get('components', {})
            for comp_name, comp_data in components_dict.items():
                if isinstance(comp_data, dict) and 'observed' in comp_data:
                    component_results[comp_data.get('obs_component', comp_name)] = comp_data
            filtered_results = self._filter_to_plot_species(component_results)
            if filtered_results:
                try:
                    boxplot_path = self._plot_residual_boxplots(filtered_results, self.figures_dir, 'best')
                    if boxplot_path:
                        generated_files.append(boxplot_path)
                except Exception as e:
                    logger.error(f"Failed to generate best residual boxplots: {e}")

        logger.info(f"Generated {len(generated_files)} summary figures")
        return generated_files

    def _plot_all_one_to_one(self,
                              component_results: Dict[str, Dict],
                              output_dir: Path,
                              label: Any) -> Optional[Path]:
        """Generate a multi-panel 1:1 plot figure."""
        if not component_results:
            return None

        n_species = len(component_results)
        if n_species == 0:
            return None

        # Determine grid layout
        n_cols = min(3, n_species)
        n_rows = int(np.ceil(n_species / n_cols))

        fig, axes = plt.subplots(n_rows, n_cols, figsize=(4*n_cols, 4*n_rows))
        if n_species == 1:
            axes = np.array([axes])
        axes = axes.flatten()

        for idx, (species_name, data) in enumerate(component_results.items()):
            if 'observed' not in data or 'simulated' not in data:
                continue

            obs = np.array(data['observed'])
            sim = np.array(data['simulated'])

            if len(obs) > 0:
                plot_one_to_one(obs, sim, species_name, ax=axes[idx])

        # Hide unused axes
        for idx in range(len(component_results), len(axes)):
            axes[idx].set_visible(False)

        fig.suptitle(f'1:1 Comparison - {label}', fontsize=12, fontweight='bold')
        plt.tight_layout()

        filepath = output_dir / f'one_to_one_{label}.png'
        fig.savefig(filepath, dpi=150, bbox_inches='tight')
        plt.close(fig)

        return filepath

    def plot_validation_panels(self,
                                processor: Any,
                                chem_obs: Any,
                                output_dir: Path,
                                label: Any,
                                components: Optional[List[str]] = None) -> Optional[Path]:
        """
        Generate 1:1 validation plots using PflotranProcessor.plot_validation.

        Args:
            processor: PflotranProcessor instance with loaded h5 file
            chem_obs: Chemical observations DataFrame
            output_dir: Directory to save figure
            label: Label for filename (e.g., iteration number)
            components: List of component names to plot. If None, uses defaults.

        Returns:
            Path to saved figure, or None if failed
        """
        # Default components matching PLOT_SPECIES
        if components is None:
            components = [
                ('Total_HCO3- [M]', 'mM', 'TIC'),
                ('Total_Fe++ [M]', 'mM', 'Fe'),
                ('Total_SO4-- [M]', 'mM', 'SO4'),
                ('Total_Ca++ [M]', 'mM', 'Ca'),
                ('pH', None, 'pH'),
            ]

        # Filter to components that exist
        available_components = []
        if hasattr(processor, 'component_list'):
            for comp_tuple in components:
                comp_name = comp_tuple[0]
                if comp_name in processor.component_list or comp_name == 'pH':
                    available_components.append(comp_tuple)
        else:
            available_components = components

        if not available_components:
            logger.warning("No valid components found for validation plots")
            return None

        n_components = len(available_components)
        n_cols = min(3, n_components)
        n_rows = int(np.ceil(n_components / n_cols))

        fig, axes = plt.subplots(n_rows, n_cols, figsize=(4*n_cols, 4*n_rows))
        if n_components == 1:
            axes = np.array([[axes]])
        axes = np.atleast_2d(axes).flatten()

        for idx, (comp_name, unit, title) in enumerate(available_components):
            try:
                processor.plot_validation(
                    component_name=comp_name,
                    startdate=self.startdate,
                    chem_obs=chem_obs,
                    ax=axes[idx],
                    unit=unit,
                    show_legend=False,
                    show_stats=True
                )
                axes[idx].set_title(title)

                # Ensure axis limits are valid (handle NaN/Inf edge cases)
                xlim = axes[idx].get_xlim()
                ylim = axes[idx].get_ylim()
                if not (np.isfinite(xlim).all() and np.isfinite(ylim).all()):
                    # Set reasonable default limits based on component type
                    if 'pH' in comp_name:
                        axes[idx].set_xlim(6, 9)
                        axes[idx].set_ylim(6, 9)
                    else:
                        axes[idx].set_xlim(0, 1)
                        axes[idx].set_ylim(0, 1)
            except Exception as e:
                logger.warning(f"Failed to plot validation for {comp_name}: {e}")
                axes[idx].set_title(f"{title}")
                # Set reasonable default limits based on component type
                if 'pH' in comp_name:
                    axes[idx].set_xlim(6, 9)
                    axes[idx].set_ylim(6, 9)
                else:
                    axes[idx].set_xlim(0, 1)
                    axes[idx].set_ylim(0, 1)
                axes[idx].text(0.5, 0.5, f"No data",
                              transform=axes[idx].transAxes, ha='center', fontsize=10)

        # Hide unused axes
        for idx in range(len(available_components), len(axes)):
            axes[idx].set_visible(False)

        fig.suptitle(f'1:1 Validation - Iteration {label}', fontsize=12, fontweight='bold')
        plt.tight_layout()

        filepath = output_dir / f'validation_1to1_{label}.png'
        fig.savefig(filepath, dpi=150, bbox_inches='tight')
        plt.close(fig)

        logger.info(f"Saved validation 1:1 plots: {filepath}")
        return filepath

    def plot_concentration_histories(self,
                                      processor: Any,
                                      chem_obs: Any,
                                      output_dir: Path,
                                      label: Any,
                                      components: Optional[List[str]] = None) -> Optional[Path]:
        """
        Generate concentration vs time history plots using PflotranProcessor.

        Args:
            processor: PflotranProcessor instance with loaded h5 file
            chem_obs: Chemical observations DataFrame
            output_dir: Directory to save figure
            label: Label for filename (e.g., iteration number)
            components: List of component names to plot. If None, uses defaults.

        Returns:
            Path to saved figure, or None if failed
        """
        # Default components matching PLOT_SPECIES
        if components is None:
            # Map observation names to simulation component names
            components = [
                'Total_HCO3- [M]',  # TIC
                'Total_Fe++ [M]',   # Fe
                'Total_SO4-- [M]',  # SO4
                'Total_Ca++ [M]',   # Ca
                'pH',               # pH
            ]

        # Filter to components that exist in the processor
        available_components = []
        if hasattr(processor, 'component_list'):
            for comp in components:
                if comp in processor.component_list or comp == 'pH':
                    available_components.append(comp)
        else:
            available_components = components

        if not available_components:
            logger.warning("No valid components found for history plots")
            return None

        n_components = len(available_components)
        fig, axes = plt.subplots(n_components, 1, figsize=(8, 3*n_components))
        if n_components == 1:
            axes = [axes]

        for idx, comp in enumerate(available_components):
            try:
                # Determine unit based on component
                if comp == 'pH':
                    unit = None  # pH is unitless
                else:
                    unit = 'mM'  # Use mM for concentrations

                processor.plot_component_histories(
                    component_name=comp,
                    ax=axes[idx],
                    startdate=self.startdate,
                    chem_obs=chem_obs,
                    unit=unit
                )
                axes[idx].set_title(comp.replace(' [M]', '').replace('Total_', ''))
                axes[idx].grid(True, alpha=0.3)

                # Ensure axis limits are valid
                xlim = axes[idx].get_xlim()
                ylim = axes[idx].get_ylim()
                if not (np.isfinite(ylim).all()):
                    axes[idx].text(0.5, 0.5, 'No valid data',
                                  transform=axes[idx].transAxes, ha='center', fontsize=10)
            except Exception as e:
                logger.warning(f"Failed to plot history for {comp}: {e}")
                axes[idx].set_title(comp.replace(' [M]', '').replace('Total_', ''))
                axes[idx].text(0.5, 0.5, f"No data",
                              transform=axes[idx].transAxes, ha='center', fontsize=10)

        fig.suptitle(f'Concentration Histories - Iteration {label}', fontsize=12, fontweight='bold')
        plt.tight_layout()

        filepath = output_dir / f'concentration_histories_{label}.png'
        fig.savefig(filepath, dpi=150, bbox_inches='tight')
        plt.close(fig)

        logger.info(f"Saved concentration histories: {filepath}")
        return filepath

    def _plot_residual_boxplots(self,
                                 component_results: Dict[str, Dict],
                                 output_dir: Path,
                                 label: Any) -> Optional[Path]:
        """Generate residual boxplots for all species using normalized residuals."""
        species_residuals = {}
        for species_name, data in component_results.items():
            if 'observed' in data and 'simulated' in data:
                obs = np.array(data['observed'])
                sim = np.array(data['simulated'])
                if len(obs) > 0:
                    residuals = sim - obs
                    # Normalize residuals by dividing by mean of observations
                    # This makes residuals comparable across different scales
                    if self.NORMALIZE_RESIDUALS:
                        mean_obs = np.mean(np.abs(obs))
                        if mean_obs > 0:
                            residuals = residuals / mean_obs
                    species_residuals[species_name] = residuals

        if not species_residuals:
            return None

        fig, ax = plt.subplots(figsize=(max(8, len(species_residuals)*1.5), 5))
        plot_residual_boxplots(species_residuals, ax=ax)

        # Update labels for normalized residuals
        if self.NORMALIZE_RESIDUALS:
            ax.set_ylabel('Normalized Residual (sim - obs) / mean(obs)')
            ax.set_title(f'Normalized Residual Distribution - {label}')
        else:
            ax.set_title(f'Residual Distribution - {label}')
        plt.tight_layout()

        filepath = output_dir / f'residual_boxplots_{label}.png'
        fig.savefig(filepath, dpi=150, bbox_inches='tight')
        plt.close(fig)

        return filepath

    def _plot_convergence(self, history: List[Dict[str, Any]]) -> Optional[Path]:
        """Generate convergence plot for the tuning run."""
        if not history:
            return None

        fig, ax = plt.subplots(figsize=(8, 5))
        plot_convergence(history, ax=ax)
        plt.tight_layout()

        filepath = self.figures_dir / 'convergence.png'
        fig.savefig(filepath, dpi=150, bbox_inches='tight')
        plt.close(fig)

        return filepath

    def _plot_species_kge_evolution(self, history: List[Dict[str, Any]]) -> Optional[Path]:
        """Plot KGE evolution for each species over iterations."""
        if not history:
            return None

        # Extract species KGE values from history
        species_kge = {}
        for h in history:
            metrics = h.get('species_metrics', {})
            for species, data in metrics.items():
                if species not in species_kge:
                    species_kge[species] = {'iterations': [], 'kge': []}
                species_kge[species]['iterations'].append(h['iteration'])
                species_kge[species]['kge'].append(data.get('KGE', np.nan))

        if not species_kge:
            return None

        fig, ax = plt.subplots(figsize=(10, 6))

        colors = get_viridis_colors(len(species_kge))
        for idx, (species, data) in enumerate(species_kge.items()):
            ax.plot(data['iterations'], data['kge'], 'o-',
                   label=species, color=colors[idx], markersize=4, linewidth=1)

        ax.axhline(y=0, color='k', linestyle='--', linewidth=0.5, alpha=0.5)
        ax.axhline(y=1, color='g', linestyle=':', linewidth=1, alpha=0.5, label='Perfect KGE')

        ax.set_xlabel('Iteration')
        ax.set_ylabel('KGE')
        ax.set_title('Species KGE Evolution')
        ax.legend(loc='best', fontsize=8, ncol=2)
        ax.grid(True, alpha=0.3)

        plt.tight_layout()

        filepath = self.figures_dir / 'species_kge_evolution.png'
        fig.savefig(filepath, dpi=150, bbox_inches='tight')
        plt.close(fig)

        return filepath


def generate_tuning_figures(h5_path: Path,
                            year: str,
                            meander: str,
                            output_dir: Path,
                            iteration: int,
                            history: Optional[List[Dict]] = None) -> List[Path]:
    """
    Convenience function to generate all tuning figures for a simulation.

    Args:
        h5_path: Path to simulation HDF5 results
        year: Simulation year
        meander: Meander identifier
        output_dir: Directory to save figures
        iteration: Current iteration number
        history: Optional full iteration history for summary plots

    Returns:
        List of paths to generated figure files
    """
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
    from processing.pflotran import PflotranProcessor
    from .config import SIMULATION_CONFIGS, get_species_for_meander

    # Get configuration
    config_key = (year, meander.lower())
    sim_config = SIMULATION_CONFIGS[config_key]
    startdate = np.datetime64(sim_config['startdate'])
    meander_code = 'MZ' if 'mz' in meander.lower() else 'MC'

    # Load observations
    obs_dir = Path('/home/christiandewey/Code/dewey-etal_meanders/data/observational/porewater')
    meander_prefix = 'mz' if 'mz' in meander.lower() else 'mc'
    obs_file = obs_dir / f'{meander_prefix}_{year}_porewater.csv'
    chem_obs = pd.read_csv(obs_file)
    chem_obs['Date'] = pd.to_datetime(chem_obs['Date'], format='mixed')

    # Initialize processor and calculate KGE
    processor = PflotranProcessor(
        h5_path=str(h5_path),
        meander=meander_code,
        perpendicular_axis='x'
    )

    kge_results = processor.calculate_kge(
        startdate=startdate,
        chem_obs=chem_obs,
        print_summary=False
    )

    # Get species metrics and objective
    tuning_species = get_species_for_meander(meander.lower())
    objective = 0.0  # Would be computed from objective function

    # Initialize visualizer and generate figures
    visualizer = TuningVisualizer(
        year=year,
        meander=meander,
        output_dir=output_dir,
        startdate=startdate
    )

    # Extract component data with obs/sim arrays
    component_results = {}
    for comp_name, comp_data in kge_results.items():
        if isinstance(comp_data, dict) and 'observed' in comp_data:
            obs_name = comp_data.get('obs_component', comp_name)
            if obs_name in tuning_species:
                component_results[obs_name] = comp_data

    generated = visualizer.generate_iteration_figures(
        iteration=iteration,
        kge_results={'component_results': component_results,
                     'species_metrics': {k: {'KGE': v.get('kge')} for k, v in component_results.items()}},
        objective=objective
    )

    # Generate summary figures if history provided
    if history:
        summary_files = visualizer.generate_summary_figures(
            history=history,
            best_kge_results=kge_results
        )
        generated.extend(summary_files)

    return generated
