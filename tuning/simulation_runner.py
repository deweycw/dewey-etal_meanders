"""
Simulation runner for PFLOTRAN parameter tuning.

This module handles:
- Generating PFLOTRAN input files with modified parameters
- Executing spin-up and transient simulations
- Managing output directories and files
- Error handling and timeouts
"""

import os
import subprocess
import shutil
import time
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple
from datetime import datetime

from .template_modifier import TemplateModifier
from .config import SIMULATION_CONFIGS, POROSITY_PARAMETERS

# Set up logging
logger = logging.getLogger(__name__)


class SimulationRunner:
    """
    Run PFLOTRAN simulations with modified parameters.

    This class handles the full simulation workflow:
    1. Modify chemistry template with new parameter values
    2. Generate input files using pflotran_generator.py
    3. Execute spin-up simulation
    4. Execute transient simulation
    5. Return path to results
    """

    # Default paths (can be overridden)
    DEFAULT_PROJECT_ROOT = Path('/home/christiandewey/Code/dewey-etal_meanders')
    DEFAULT_SIMULATIONS_DIR = DEFAULT_PROJECT_ROOT / 'pflotran' / 'simulations'

    # PFLOTRAN_DIR is the base directory; executable is at src/pflotran/pflotran
    _PFLOTRAN_DIR = os.environ.get('PFLOTRAN_DIR', '/home/christiandewey/Code/pflotran')
    DEFAULT_PFLOTRAN_EXE = str(Path(_PFLOTRAN_DIR) / 'src' / 'pflotran' / 'pflotran')

    def __init__(self,
                 year: str,
                 meander: str,
                 project_root: Optional[Path] = None,
                 pflotran_exe: Optional[str] = None,
                 n_cores: int = 14,
                 timeout_minutes: int = 120,
                 reference_checkpoint: Optional[Path] = None):
        """
        Initialize the simulation runner.

        Args:
            year: Simulation year ('2018' or '2019')
            meander: Meander identifier ('mzt' or 'mcp')
            project_root: Root directory of the project
            pflotran_exe: Path to PFLOTRAN executable
            n_cores: Number of cores for MPI execution
            timeout_minutes: Maximum time per simulation in minutes
            reference_checkpoint: Optional path to a pre-computed spin checkpoint.
                If provided, spin simulations will be skipped and this checkpoint
                will be used instead. This speeds up tuning iterations significantly.
        """
        self.year = year
        self.meander = meander.lower()
        self.project_root = project_root or self.DEFAULT_PROJECT_ROOT
        self.simulations_dir = self.project_root / 'pflotran' / 'simulations'
        self.pflotran_exe = pflotran_exe or self.DEFAULT_PFLOTRAN_EXE
        self.n_cores = n_cores
        self.timeout_seconds = timeout_minutes * 60
        self.reference_checkpoint = Path(reference_checkpoint) if reference_checkpoint else None

        # Validate reference checkpoint if provided
        if self.reference_checkpoint and not self.reference_checkpoint.exists():
            raise FileNotFoundError(f"Reference checkpoint not found: {self.reference_checkpoint}")

        # Get simulation config
        config_key = (year, self.meander)
        if config_key not in SIMULATION_CONFIGS:
            raise ValueError(f"Invalid year/meander combination: {config_key}")
        self.sim_config = SIMULATION_CONFIGS[config_key]

        # Template paths
        self.template_chemistry = self.simulations_dir / 'TEMPLATE-chemistry.txt'
        self.template_pflotran = self.simulations_dir / 'TEMPLATE-pflotran.in'

        # Track which parameters are porosity (handled separately)
        self.porosity_param_names = {p.name for p in POROSITY_PARAMETERS}

    def run_simulation(self,
                       param_values: Dict[str, float],
                       run_id: Optional[str] = None,
                       keep_files: bool = False) -> Tuple[Optional[Path], dict]:
        """
        Run a full PFLOTRAN simulation with the given parameters.

        Args:
            param_values: Dictionary mapping parameter names to values.
            run_id: Optional identifier for this run. If None, uses timestamp.
            keep_files: If True, keep all output files. If False, clean up
                       intermediate files after extracting results.

        Returns:
            Tuple of (h5_path, metadata) where h5_path is the path to the
            transient simulation results HDF5 file, or None if simulation failed.
            metadata dict contains timing, status, and error information.
        """
        start_time = time.time()
        metadata = {
            'param_values': param_values,
            'run_id': run_id,
            'year': self.year,
            'meander': self.meander,
            'start_time': datetime.now().isoformat(),
            'status': 'running',
            'error': None,
            'spin_time': None,
            'transient_time': None,
            'total_time': None,
        }

        if run_id is None:
            run_id = datetime.now().strftime('%Y%m%d_%H%M%S')

        try:
            # Separate chemistry parameters from porosity parameters
            chem_params = {k: v for k, v in param_values.items()
                          if k not in self.porosity_param_names}
            porosity_params = {k: v for k, v in param_values.items()
                              if k in self.porosity_param_names}

            # Step 1: Create temporary modified chemistry template
            logger.info(f"Run {run_id}: Modifying chemistry template")
            temp_chem_path = self._create_modified_template(chem_params, run_id)

            # Step 1b: Create modified PFLOTRAN template if porosity params present
            temp_pflotran_path = None
            if porosity_params:
                logger.info(f"Run {run_id}: Modifying porosity values")
                temp_pflotran_path = self._create_modified_pflotran_template(porosity_params, run_id)

            # Step 2: Generate input files
            logger.info(f"Run {run_id}: Generating input files")
            output_dir = self._generate_input_files(temp_chem_path, run_id, temp_pflotran_path)
            metadata['output_dir'] = str(output_dir)

            # Step 3: Run spin-up simulation OR use reference checkpoint
            if self.reference_checkpoint:
                # Skip spin and use pre-computed checkpoint
                logger.info(f"Run {run_id}: Using reference checkpoint (skipping spin)")
                spin_start = time.time()
                spin_success = self._copy_reference_checkpoint(output_dir)
                metadata['spin_time'] = time.time() - spin_start
                metadata['used_reference_checkpoint'] = True
            else:
                # Run full spin-up simulation
                logger.info(f"Run {run_id}: Running spin-up simulation")
                spin_start = time.time()
                spin_success = self._run_pflotran(output_dir, is_spinup=True)
                metadata['spin_time'] = time.time() - spin_start
                metadata['used_reference_checkpoint'] = False

            if not spin_success:
                metadata['status'] = 'spin_failed'
                metadata['error'] = 'Spin-up simulation failed' if not self.reference_checkpoint else 'Failed to copy reference checkpoint'
                logger.error(f"Run {run_id}: Spin-up failed")
                return None, metadata

            # Step 4: Run transient simulation
            logger.info(f"Run {run_id}: Running transient simulation")
            trans_start = time.time()
            trans_success = self._run_pflotran(output_dir, is_spinup=False)
            metadata['transient_time'] = time.time() - trans_start

            if not trans_success:
                metadata['status'] = 'transient_failed'
                metadata['error'] = 'Transient simulation failed'
                logger.error(f"Run {run_id}: Transient simulation failed")
                return None, metadata

            # Step 5: Find the output HDF5 file
            h5_path = self._find_h5_output(output_dir)
            if h5_path is None:
                metadata['status'] = 'no_output'
                metadata['error'] = 'No HDF5 output file found'
                return None, metadata

            metadata['h5_path'] = str(h5_path)
            metadata['status'] = 'success'
            metadata['total_time'] = time.time() - start_time

            # Clean up temporary files if requested
            if not keep_files:
                self._cleanup(output_dir, h5_path)

            logger.info(f"Run {run_id}: Completed successfully in {metadata['total_time']:.1f}s")
            return h5_path, metadata

        except Exception as e:
            metadata['status'] = 'error'
            metadata['error'] = str(e)
            metadata['total_time'] = time.time() - start_time
            logger.exception(f"Run {run_id}: Exception occurred")
            return None, metadata

    def _create_modified_template(self,
                                   param_values: Dict[str, float],
                                   run_id: str) -> Path:
        """Create a modified chemistry template with new parameter values."""
        modifier = TemplateModifier(self.template_chemistry)
        modifier.modify_parameters(param_values)

        # Write to a temporary file in the simulations directory
        temp_path = self.simulations_dir / f'TEMPLATE-chemistry-{run_id}.txt'
        modifier.write(temp_path)

        return temp_path

    def _create_modified_pflotran_template(self,
                                            porosity_params: Dict[str, float],
                                            run_id: str) -> Path:
        """Create a modified PFLOTRAN template with new porosity values."""
        import re

        content = self.template_pflotran.read_text()

        # Replace gravel porosity
        if 'gravel_porosity' in porosity_params:
            # Match POROSITY line within gravel material block
            pattern = r'(MATERIAL_PROPERTY\s+gravel.*?POROSITY\s+)[\d.]+'
            replacement = rf'\g<1>{porosity_params["gravel_porosity"]:.3f}'
            content = re.sub(pattern, replacement, content, flags=re.DOTALL)

        # Replace topsoil porosity
        if 'topsoil_porosity' in porosity_params:
            # Match POROSITY line within topsoil material block
            pattern = r'(MATERIAL_PROPERTY\s+topsoil.*?POROSITY\s+)[\d.]+'
            replacement = rf'\g<1>{porosity_params["topsoil_porosity"]:.3f}'
            content = re.sub(pattern, replacement, content, flags=re.DOTALL)

        # Write to a temporary file
        temp_path = self.simulations_dir / f'TEMPLATE-pflotran-{run_id}.in'
        temp_path.write_text(content)

        return temp_path

    def _generate_input_files(self,
                               chem_template_path: Path,
                               run_id: str,
                               pflotran_template_path: Optional[Path] = None) -> Path:
        """
        Generate PFLOTRAN input files using pflotran_generator.py.

        Args:
            chem_template_path: Path to modified chemistry template
            run_id: Run identifier
            pflotran_template_path: Optional path to modified PFLOTRAN template (for porosity)

        Returns the output directory containing the generated files.
        """
        generator_script = self.simulations_dir / 'pflotran_generator.py'

        # Temporarily replace the chemistry template
        original_chem = self.template_chemistry
        backup_chem = original_chem.with_suffix('.txt.bak')

        # Also handle PFLOTRAN template if provided
        original_pflotran = self.template_pflotran
        backup_pflotran = original_pflotran.with_suffix('.in.bak')

        try:
            # Backup original and replace with modified chemistry template
            shutil.copy(original_chem, backup_chem)
            shutil.copy(chem_template_path, original_chem)

            # Backup and replace PFLOTRAN template if provided
            if pflotran_template_path:
                shutil.copy(original_pflotran, backup_pflotran)
                shutil.copy(pflotran_template_path, original_pflotran)

            # Run the generator
            # Use --keep-tuning-markers since TemplateModifier handles $T substitution
            cmd = [
                'python', str(generator_script),
                '--year', self.year,
                '--meander', self.meander,
                '--keep-tuning-markers'
            ]

            result = subprocess.run(
                cmd,
                cwd=str(self.simulations_dir),
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout for generation
            )

            if result.returncode != 0:
                logger.error(f"Generator failed: {result.stderr}")
                raise RuntimeError(f"Input file generation failed: {result.stderr}")

            # Find the newest output directory
            subdir = self.simulations_dir / self.sim_config['subdir']
            date_dirs = sorted(subdir.glob('????-??-??'), reverse=True)
            if not date_dirs:
                raise RuntimeError("No output directory created")

            time_dirs = sorted(date_dirs[0].glob('????-??-??_??-??-??'), reverse=True)
            if not time_dirs:
                raise RuntimeError("No timestamped directory created")

            output_dir = time_dirs[0]
            logger.info(f"Generated input files in {output_dir}")

            return output_dir

        finally:
            # Restore original chemistry template
            if backup_chem.exists():
                shutil.move(backup_chem, original_chem)
            # Clean up temporary chemistry template
            if chem_template_path.exists() and 'TEMPLATE-chemistry-' in chem_template_path.name:
                chem_template_path.unlink()

            # Restore original PFLOTRAN template if it was modified
            if backup_pflotran.exists():
                shutil.move(backup_pflotran, original_pflotran)
            # Clean up temporary PFLOTRAN template
            if pflotran_template_path and pflotran_template_path.exists():
                if 'TEMPLATE-pflotran-' in pflotran_template_path.name:
                    pflotran_template_path.unlink()

    def _copy_reference_checkpoint(self, output_dir: Path) -> bool:
        """
        Copy the reference checkpoint to the output directory with the expected filename.

        The transient input file expects a restart checkpoint with a specific name
        (e.g., pflotran-mcp19_2026-02-02_10-03-44_spin-restart.chk). This method
        copies the reference checkpoint to that location.

        Args:
            output_dir: Directory containing the generated input files

        Returns:
            True if checkpoint was copied successfully, False otherwise.
        """
        try:
            # Find the transient input file to extract the expected checkpoint name
            transient_files = [f for f in output_dir.glob('pflotran-*.in')
                             if '_spin.in' not in f.name]
            if not transient_files:
                logger.error("No transient input file found")
                return False

            transient_file = transient_files[0]

            # Read the transient file to find the expected RESTART FILENAME
            with open(transient_file, 'r') as f:
                content = f.read()

            # Find the RESTART FILENAME line
            import re
            match = re.search(r'FILENAME\s+(\S+restart\.chk)', content)
            if not match:
                logger.error("Could not find RESTART FILENAME in transient input file")
                return False

            expected_checkpoint_name = match.group(1)
            target_path = output_dir / expected_checkpoint_name

            # Copy the reference checkpoint
            logger.info(f"Copying reference checkpoint to {target_path.name}")
            shutil.copy2(self.reference_checkpoint, target_path)

            return True

        except Exception as e:
            logger.exception(f"Error copying reference checkpoint: {e}")
            return False

    def _run_pflotran(self, output_dir: Path, is_spinup: bool = False) -> bool:
        """
        Execute a PFLOTRAN simulation.

        Args:
            output_dir: Directory containing input files
            is_spinup: If True, run spin-up. If False, run transient.

        Returns:
            True if simulation completed successfully, False otherwise.
        """
        # Find the input file
        suffix = '_spin.in' if is_spinup else '.in'
        input_files = list(output_dir.glob(f'pflotran-*{suffix}'))

        # Filter out spin files when looking for transient
        if not is_spinup:
            input_files = [f for f in input_files if '_spin.in' not in f.name]

        if not input_files:
            logger.error(f"No input file found matching *{suffix}")
            return False

        input_file = input_files[0]
        logger.info(f"Running PFLOTRAN with input: {input_file.name}")

        # Build command
        if self.n_cores > 1:
            cmd = [
                'mpirun', '-np', str(self.n_cores),
                self.pflotran_exe,
                '-pflotranin', str(input_file)
            ]
        else:
            cmd = [
                self.pflotran_exe,
                '-pflotranin', str(input_file)
            ]

        # Run simulation
        try:
            result = subprocess.run(
                cmd,
                cwd=str(output_dir),
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds
            )

            # Check for success
            if result.returncode != 0:
                logger.error(f"PFLOTRAN exited with code {result.returncode}")
                logger.error(f"STDERR: {result.stderr[-2000:]}")  # Last 2000 chars
                return False

            # Check for convergence issues in output
            if 'CONVERGENCE' in result.stdout and 'NOT' in result.stdout:
                logger.warning("Possible convergence issues detected")

            return True

        except subprocess.TimeoutExpired:
            logger.error(f"Simulation timed out after {self.timeout_seconds}s")
            return False
        except Exception as e:
            logger.exception(f"Error running PFLOTRAN: {e}")
            return False

    def _find_h5_output(self, output_dir: Path) -> Optional[Path]:
        """Find the transient simulation HDF5 output file."""
        # Look for .h5 files that are NOT spin-up results
        h5_files = list(output_dir.glob('*.h5'))
        h5_files = [f for f in h5_files if '_spin' not in f.name and 'grid' not in f.name.lower()]

        if not h5_files:
            return None

        # Return the most recent one
        return max(h5_files, key=lambda p: p.stat().st_mtime)

    def _cleanup(self, output_dir: Path, keep_h5: Path):
        """Clean up intermediate files, keeping only the HDF5 results."""
        # Files to keep
        keep_patterns = ['*.h5', 'generation.log']

        for f in output_dir.iterdir():
            if f == keep_h5:
                continue
            if f.is_file():
                if not any(f.match(p) for p in keep_patterns):
                    f.unlink()
            elif f.is_dir():
                shutil.rmtree(f)


def run_single_simulation(param_values: Dict[str, float],
                          year: str = '2019',
                          meander: str = 'mzt',
                          **kwargs) -> Tuple[Optional[Path], dict]:
    """
    Convenience function to run a single simulation.

    Args:
        param_values: Parameter name -> value dictionary
        year: Simulation year
        meander: Meander identifier
        **kwargs: Additional arguments to SimulationRunner

    Returns:
        Tuple of (h5_path, metadata)
    """
    runner = SimulationRunner(year=year, meander=meander, **kwargs)
    return runner.run_simulation(param_values)


def generate_reference_checkpoint(year: str = '2019',
                                   meander: str = 'mzt',
                                   output_path: Optional[Path] = None,
                                   **kwargs) -> Optional[Path]:
    """
    Generate a reference spin checkpoint for use in fast tuning mode.

    This runs a single spin simulation with default parameters and saves
    the resulting checkpoint file. This checkpoint can then be used with
    the reference_checkpoint parameter to skip spin simulations during
    parameter tuning, significantly speeding up each iteration.

    Args:
        year: Simulation year ('2018' or '2019')
        meander: Meander identifier ('mzt' or 'mcp')
        output_path: Where to save the checkpoint. If None, saves to
            simulations/{meander}{year[-2:]}/reference_spin_checkpoint.chk
        **kwargs: Additional arguments to SimulationRunner

    Returns:
        Path to the generated checkpoint file, or None if generation failed.

    Example:
        >>> # Generate reference checkpoint
        >>> checkpoint = generate_reference_checkpoint(year='2019', meander='mcp')
        >>> print(f"Checkpoint saved to: {checkpoint}")
        >>>
        >>> # Use it for fast tuning
        >>> from tuning.agent import run_agent_tuning
        >>> results = run_agent_tuning(
        ...     year='2019',
        ...     meander='mcp',
        ...     reference_checkpoint=checkpoint
        ... )
    """
    from .config import PARAM_BY_NAME, get_parameters_for_meander

    logger.info(f"Generating reference checkpoint for {meander} {year}")

    # Get default parameter values
    param_names = get_parameters_for_meander(meander)
    default_params = {name: PARAM_BY_NAME[name].default for name in param_names}

    # Create runner (without reference checkpoint - we want to run the full spin)
    runner = SimulationRunner(year=year, meander=meander, **kwargs)

    # Run spin-only simulation
    run_id = f"reference_spin_{meander}{year[-2:]}"
    logger.info(f"Running spin simulation with default parameters...")

    try:
        # Generate input files
        from .template_modifier import TemplateModifier

        chem_params = {k: v for k, v in default_params.items()
                      if k not in runner.porosity_param_names}

        temp_chem_path = runner._create_modified_template(chem_params, run_id)
        output_dir = runner._generate_input_files(temp_chem_path, run_id)

        # Run spin simulation
        logger.info("Running spin-up simulation (this may take 1-2 hours)...")
        spin_success = runner._run_pflotran(output_dir, is_spinup=True)

        if not spin_success:
            logger.error("Spin simulation failed")
            return None

        # Find the restart checkpoint
        restart_files = list(output_dir.glob('*-restart.chk'))
        if not restart_files:
            logger.error("No restart checkpoint file found after spin")
            return None

        source_checkpoint = restart_files[0]

        # Determine output path
        if output_path is None:
            output_path = (runner.simulations_dir / runner.sim_config['subdir'] /
                          f'reference_spin_checkpoint.chk')

        # Copy checkpoint to output location
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_checkpoint, output_path)

        logger.info(f"Reference checkpoint saved to: {output_path}")
        logger.info(f"Use this with: reference_checkpoint='{output_path}'")

        return output_path

    except Exception as e:
        logger.exception(f"Error generating reference checkpoint: {e}")
        return None
