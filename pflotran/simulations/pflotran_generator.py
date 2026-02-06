#!/usr/bin/env python3
"""
PFLOTRAN Input File Generator for Meander Simulations

This script generates PFLOTRAN input files for both spin-up and transient simulations
using boundary condition data and template files. All outputs are saved to a nested
date-time directory structure within the appropriate meander/year subdirectory.

Requirements:
- pandas
- datetime
- os

Directory Structure:
simulations/
├── pflotran_generator.py       # This script
├── chem-bcs/                   # Shared chemical boundary condition CSV files
├── hydro-bcs/                  # Shared hydrological boundary condition files
│   ├── hydro_us_*.txt          # Upstream hydro data (MZT)
│   ├── hydro_ds_*.txt          # Downstream hydro data (MZT)
│   ├── mc_us_*.txt             # Upstream hydro data (MCP)
│   └── mc_dn_*.txt             # Downstream hydro data (MCP)
├── TEMPLATE-constraint.txt     # Chemistry constraint template
├── TEMPLATE-chemistry.txt      # Chemistry block template
├── TEMPLATE-pflotran.in        # Main PFLOTRAN template
├── TEMPLATE-pflotran-spin.in   # Spin-up template
├── mcp18/                      # Meander C 2018 output directory
├── mcp19/                      # Meander C 2019 output directory
├── mzt18/                      # Meander Z 2018 output directory
└── mzt19/                      # Meander Z 2019 output directory

Usage:
    python pflotran_generator.py --year YEAR --meander MEANDER

Examples:
    python pflotran_generator.py --year 2019 --meander mzt
    python pflotran_generator.py --year 2018 --meander mcp

Author: Christian Dewey
Date: 01.01.2026
Version: 3.0 - Unified generator for all meander/year combinations
"""

import os
import pandas as pd
import warnings
from datetime import datetime
import argparse
from typing import Dict, Tuple, List
from pathlib import Path
import shutil

warnings.filterwarnings('ignore')

# Constants
MOLECULAR_WEIGHTS = {
    'aluminum': 26.982, 'calcium': 40.078, 'chloride': 35.453,
    'iron': 55.845, 'dic': 12.011, 'potassium': 39.098,
    'magnesium': 24.305, 'sodium': 22.990, 'nitrate': 62.0049,
    'silicon': 62.0049, 'sulfate': 96.06, 'npoc': 12.011
}

YEAR_CONFIGS = {
    '2018': {
        'start': pd.Timestamp(2018, 4, 1),
        'end': pd.Timestamp(2018, 10, 31)
    },
    '2019': {
        'start': pd.Timestamp(2019, 4, 19),
        'end': pd.Timestamp(2019, 10, 2)
    }
}

# Configuration lookup tables based on year and meander
SIMULATION_CONFIGS = {
    ('2019', 'mzt'): {
        'nx': 108,
        'upstream_h': 1.94,
        'downstream_h': 1.66,
        'upstream_file': 'hydro_us_2019_4-21_10-2-MZT.txt',
        'downstream_file': 'hydro_ds_2019_4-21_10-2-MZT.txt',
        'subdir': 'mzt19',
        'final_time': 3993  # hours
    },
    ('2018', 'mzt'): {
        'nx': 108,
        'upstream_h': 1.84,
        'downstream_h': 1.46,
        'upstream_file': 'hydro_us_2018_4-1_10-31-MZT.txt',
        'downstream_file': 'hydro_ds_2018_4-1_10-31-MZT.txt',
        'subdir': 'mzt18',
        'final_time': 5131  # hours
    },
    ('2019', 'mcp'): {
        'nx': 122,
        'upstream_h': 1.94,
        'downstream_h': 0.91,
        'upstream_file': 'mc_up_2019_3993h.txt',
        'downstream_file': 'mc_dn_2019_3993h.txt',
        'subdir': 'mcp19',
        'final_time': 3993  # hours
    },
    ('2018', 'mcp'): {
        'nx': 122,
        'upstream_h': 1.84,
        'downstream_h': 0.96,
        'upstream_file': 'mc_us_2018_5131h-NODAM.txt',
        'downstream_file': 'mc_dn_2018_5131h-NODAM.txt',
        'subdir': 'mcp18',
        'final_time': 5131  # hours
    }
}


class PFLOTRANGenerator:
    """Main class for generating PFLOTRAN input files with corrected DATUM calculations."""

    def __init__(self, year: str, meander: str, nx: int, upstream_h: float,
                 downstream_h: float, final_time: int, sim_dir: Path, template_dir: Path,
                 strip_tuning_markers: bool = True):
        """
        Initialize the PFLOTRAN generator.

        Args:
            year: Simulation year ('2018' or '2019')
            meander: Meander type ('mcp' or 'mzt')
            nx: Number of grid cells in x direction
            upstream_h: Upstream hydraulic head
            downstream_h: Downstream hydraulic head
            final_time: Simulation duration in hours
            sim_dir: The simulation subdirectory (e.g., mcp18, mzt19)
            template_dir: Directory containing shared templates
            strip_tuning_markers: If True, remove $T markers from chemistry template
                                  (use True for standalone runs, False for tuning workflow)
        """
        self.year = year
        self.meander = meander.lower()
        self.nx = nx
        self.upstream_h = upstream_h
        self.downstream_h = downstream_h
        self.final_time = final_time  # Simulation duration in hours
        self.sim_dir = sim_dir  # The simulation subdirectory (e.g., mcp18, mzt19)
        self.template_dir = template_dir  # Directory containing shared templates
        self.strip_tuning_markers = strip_tuning_markers
        self.bc_data = None
        self.chemistry_block = None

        # Create nested date-time output directory within sim_dir
        self.output_dir = self._create_output_directory()

        self.validate_inputs()
        self.load_chemistry_template()

    def _create_output_directory(self) -> Path:
        """Create nested date-time based output directory within sim_dir."""
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        datetime_str = now.strftime("%Y-%m-%d_%H-%M-%S")

        # Create nested directory structure within sim_dir
        date_dir = self.sim_dir / date_str
        output_dir = date_dir / datetime_str

        # Store the timestamp for consistent use in file headers
        self.generation_timestamp = now

        # Create directories if they don't exist
        output_dir.mkdir(parents=True, exist_ok=True)

        print(f"Output directory: {output_dir.absolute()}")
        print(f"Local timestamp: {now.strftime('%Y-%m-%d %H:%M:%S')}")
        return output_dir

    def validate_inputs(self):
        """Validate input parameters and required files."""
        if self.year not in YEAR_CONFIGS:
            raise ValueError(f"Year must be one of {list(YEAR_CONFIGS.keys())}")

        if self.meander not in ['mcp', 'mzt']:
            raise ValueError(f"Meander must be one of ['mcp', 'mzt'], got: {self.meander}")

        required_files = [
            'TEMPLATE-constraint.txt',
            'TEMPLATE-chemistry.txt',
            'TEMPLATE-pflotran.in',
            'TEMPLATE-pflotran-spin.in'
        ]

        for file in required_files:
            filepath = self.template_dir / file
            if not filepath.exists():
                raise FileNotFoundError(f"Required template file not found: {filepath}")

        chem_bcs_dir = self.template_dir / 'chem-bcs'
        if not chem_bcs_dir.exists():
            raise FileNotFoundError(f"Directory not found: {chem_bcs_dir}")

        hydro_bcs_dir = self.template_dir / 'hydro-bcs'
        if not hydro_bcs_dir.exists():
            raise FileNotFoundError(f"Directory not found: {hydro_bcs_dir}")

    def load_chemistry_template(self):
        """Load the chemistry template file.

        If strip_tuning_markers is True, removes the $T markers from tunable
        parameter lines, keeping the default values. This allows the generator
        to produce valid PFLOTRAN input files when run standalone (not as part
        of a tuning workflow).
        """
        print("Loading chemistry template...")
        try:
            template_path = self.template_dir / 'TEMPLATE-chemistry.txt'
            with open(template_path, 'r') as f:
                lines = f.readlines()

            if self.strip_tuning_markers:
                # Remove $T markers from tunable parameter lines
                # Format: "        $T KEYWORD value" -> "        KEYWORD value"
                stripped_lines = []
                marker_count = 0
                for line in lines:
                    if '$T ' in line:
                        # Remove the $T marker but keep the rest of the line
                        stripped_lines.append(line.replace('$T ', ''))
                        marker_count += 1
                    else:
                        stripped_lines.append(line)
                self.chemistry_block = stripped_lines
                print(f"  Chemistry template loaded ({len(self.chemistry_block)} lines)")
                print(f"  Stripped {marker_count} tuning markers ($T) for standalone run")
            else:
                self.chemistry_block = lines
                print(f"  Chemistry template loaded ({len(self.chemistry_block)} lines)")
                print(f"  Tuning markers ($T) preserved for tuning workflow")

        except Exception as e:
            raise FileNotFoundError(f"Failed to load chemistry template: {e}")

    def load_bc_data(self) -> Dict[str, pd.DataFrame]:
        """Load and process boundary condition data efficiently."""
        print("Loading boundary condition data...")
        print(f"Target year: {self.year}")
        print(f"Meander: {self.meander.upper()}")
        year_config = YEAR_CONFIGS[self.year]
        print(f"Date range: {year_config['start']} to {year_config['end']}")

        bc_data = {}
        chem_bcs_dir = self.template_dir / 'chem-bcs'
        csv_files = [f for f in os.listdir(chem_bcs_dir) if f.endswith('.csv')]

        if not csv_files:
            raise FileNotFoundError(f"No CSV files found in '{chem_bcs_dir}'")

        for filename in csv_files:
            try:
                filepath = chem_bcs_dir / filename
                data = pd.read_csv(filepath)

                component = filename.split('.')[0].split('_')[-1]

                print(f"\n  Processing {component} from {filename}:")
                print(f"    Raw data shape: {data.shape}")

                unit = data.iloc[0, 1]
                print(f"    Unit: {unit}")

                df = data[1:].copy()
                print(f"    After removing header: {len(df)} rows")

                df['date'] = pd.to_datetime(df['date'], errors='coerce')
                print(f"    After date parsing: {len(df.dropna(subset=['date']))} valid dates")

                df[component] = pd.to_numeric(df[component], errors='coerce')
                print(f"    After numeric conversion: {len(df.dropna(subset=[component]))} valid values")

                df = df.dropna()
                print(f"    After removing NaN: {len(df)} rows")

                if len(df) > 0:
                    print(f"    Date range in data: {df['date'].min()} to {df['date'].max()}")

                conversion_factor = self._get_conversion_factor(component, unit)
                print(f"    Conversion factor: {conversion_factor}")

                interpolated_data = self._interpolate_data(df, component, conversion_factor)
                print(f"    After interpolation: {len(interpolated_data)} rows")

                time_filtered = interpolated_data[
                    (interpolated_data['date'] >= year_config['start']) &
                    (interpolated_data['date'] <= year_config['end'])
                ]
                print(f"    After year filtering: {len(time_filtered)} rows")

                if len(time_filtered) > 0:
                    print(f"    Final date range: {time_filtered['date'].min()} to {time_filtered['date'].max()}")
                else:
                    print(f"    No data remains after filtering for year {self.year}")
                    if len(interpolated_data) > 0:
                        print(f"    Available date range: {interpolated_data['date'].min()} to {interpolated_data['date'].max()}")

                bc_data[component] = time_filtered
                print(f"  {component} loaded ({len(time_filtered)} data points)")

            except Exception as e:
                print(f"  Failed to load {component}: {e}")
                import traceback
                traceback.print_exc()

        if 'nitrate' in bc_data:
            self._fix_nitrate_data(bc_data['nitrate'])

        components_with_no_data = [comp for comp, df in bc_data.items() if len(df) == 0]
        if len(components_with_no_data) > 0:
            print(f"\n  Components with no data after filtering: {components_with_no_data}")
            self._validate_bc_data(bc_data)

        self.bc_data = bc_data
        return bc_data

    def _validate_bc_data(self, bc_data: Dict[str, pd.DataFrame]) -> None:
        """Validate boundary condition data and add fallback values for missing components."""
        required_components = [
            'pH', 'aluminum', 'calcium', 'chloride', 'dic',
            'potassium', 'magnesium', 'sodium', 'nitrate',
            'silicon', 'sulfate', 'npoc'
        ]

        fallback_values = {
            'pH': 7.0, 'aluminum': 1e-9, 'calcium': 1e-6, 'chloride': 1e-6,
            'dic': 1e-6, 'potassium': 1e-7, 'magnesium': 1e-7, 'sodium': 1e-6,
            'nitrate': 1e-8, 'silicon': 1e-8, 'sulfate': 1e-7, 'npoc': 1e-9
        }

        year_config = YEAR_CONFIGS[self.year]
        total_days = int((year_config['end'] - year_config['start']).total_seconds() / 3600 / 24)

        for component in required_components:
            if component not in bc_data or len(bc_data[component]) == 0:
                print(f"  No data for {component}, using fallback value: {fallback_values[component]}")

                dates = pd.date_range(year_config['start'], year_config['end'], freq='D')
                fallback_df = pd.DataFrame({
                    'date': dates,
                    f'{component}_M': [fallback_values[component]] * len(dates)
                })
                bc_data[component] = fallback_df

            elif len(bc_data[component]) < total_days * 0.5:
                print(f"  Insufficient data for {component} ({len(bc_data[component])} points), " +
                      f"extending with fallback value: {fallback_values[component]}")

                existing_df = bc_data[component]
                last_value = existing_df.iloc[-1, 1] if len(existing_df) > 0 else fallback_values[component]

                dates = pd.date_range(year_config['start'], year_config['end'], freq='D')
                extended_df = pd.DataFrame({
                    'date': dates,
                    f'{component}_M': [last_value] * len(dates)
                })
                bc_data[component] = extended_df

    def _get_conversion_factor(self, component: str, unit: str) -> float:
        """Calculate unit conversion factor."""
        mw = MOLECULAR_WEIGHTS.get(component, 1.0)

        conversion_map = {
            'ppm': 1000 * mw,
            'ppb': 1e6 * mw,
            'mg.L-1': 1000 * mw,
            'uM': 1e6,
            'pH': 1
        }

        return conversion_map.get(unit, 1.0)

    def _interpolate_data(self, df: pd.DataFrame, component: str, conversion: float) -> pd.DataFrame:
        """Efficiently interpolate data for gaps > 24 hours."""
        interpolated = []

        for i in range(len(df) - 1):
            current_date = df['date'].iloc[i]
            current_conc = df[component].iloc[i] / conversion
            next_date = df['date'].iloc[i + 1]
            next_conc = df[component].iloc[i + 1] / conversion

            interpolated.append([current_date, current_conc])

            diff_hours = (next_date - current_date).total_seconds() / 3600

            if diff_hours > 24:
                days_between = int(diff_hours / 24)
                delta_conc = (next_conc - current_conc) / days_between

                for day in range(1, days_between):
                    interp_date = current_date + pd.Timedelta(days=day)
                    interp_conc = current_conc + (delta_conc * day)
                    interpolated.append([interp_date, interp_conc])

        return pd.DataFrame(interpolated, columns=['date', f'{component}_M'])

    def _fix_nitrate_data(self, nitrate_df: pd.DataFrame):
        """Fix zero or negative nitrate values.

        PFLOTRAN chemistry solver cannot handle exactly zero concentrations.
        Replace zeros/negatives with previous value or a minimum floor.
        """
        column = 'nitrate_M'
        min_floor = 1e-12  # Minimum concentration floor to prevent solver issues

        # Fix first value if zero/negative
        if len(nitrate_df) > 0 and nitrate_df[column].iloc[0] <= 0.0:
            nitrate_df[column].iloc[0] = min_floor

        # Fix subsequent values
        for i in range(1, len(nitrate_df)):
            if nitrate_df[column].iloc[i] <= 0.0:
                prev_val = nitrate_df[column].iloc[i-1]
                nitrate_df[column].iloc[i] = max(prev_val, min_floor)

    def write_chemistry_blocks(self, block_type: str = 'river') -> Tuple[List[str], List[str]]:
        """Write chemistry and transport constraint blocks."""
        print(f"Writing {block_type} chemistry blocks...")

        chem_file = self.output_dir / f'{block_type}_chem.txt'
        transport_file = self.output_dir / f'{block_type}_transport_constraint.txt'

        for file in [chem_file, transport_file]:
            if file.exists():
                file.unlink()

        template_path = self.template_dir / 'TEMPLATE-constraint.txt'
        with open(template_path, 'r') as f:
            template = f.readlines()

        if not self.bc_data:
            self.load_bc_data()

        year_config = YEAR_CONFIGS[self.year]
        diff_days = int((year_config['end'] - year_config['start']).total_seconds() / 3600 / 24)

        for day in range(diff_days - 1):
            template[0] = f'\nCONSTRAINT  from_{block_type}_conc_{day*24}\n'
            self._update_template_concentrations(template, day)

            with open(chem_file, 'a') as f:
                f.writelines(template)

        transport_type = 'dirichlet_zero_gradient' if block_type == 'river' else 'zero_gradient'

        start_string = (f'\nTRANSPORT_CONDITION  from_{block_type}\n'
                       f'    TIME_UNITS h\n'
                       f'    TYPE {transport_type}\n'
                       f'     CONSTRAINT_LIST\n')

        with open(transport_file, 'a') as f:
            f.write(start_string)
            for day in range(diff_days - 1):
                f.write(f'      {day*24}.d0  from_{block_type}_conc_{day*24}\n')
            f.write('    /\nEND\n')

        with open(chem_file, 'r') as f:
            chem_blocks = f.readlines()

        with open(transport_file, 'r') as f:
            transport_blocks = f.readlines()

        return chem_blocks, transport_blocks

    def _update_template_concentrations(self, template: List[str], day: int):
        """Update template with concentration values for given day."""
        bc = self.bc_data
        min_floor = 1e-12  # Minimum concentration floor to prevent solver issues

        def get_concentration(component: str, day_index: int) -> float:
            if component not in bc or len(bc[component]) == 0:
                return 1e-9
            max_index = len(bc[component]) - 1
            safe_index = min(day_index, max_index)
            try:
                value = bc[component].iloc[safe_index, 1]
                # Ensure no zero or negative concentrations (breaks chemistry solver)
                return max(value, min_floor) if value > 0 else min_floor
            except (IndexError, KeyError):
                return 1e-9

        template[2] = f'    H+          {get_concentration("pH", day):.2f}  P\n'
        template[5] = f'    Al+++       {get_concentration("aluminum", day):.2e}  T\n'
        template[6] = f'    Ca++        {get_concentration("calcium", day):.2e}  T\n'
        template[7] = f'    Cl-         {get_concentration("chloride", day):.2e}  T\n'
        template[10] = f'    HCO3-       {get_concentration("dic", day):.2e}  T\n'
        template[12] = f'    K+          {get_concentration("potassium", day):.2e}  T\n'
        template[13] = f'    Mg++        {get_concentration("magnesium", day):.2e}  T\n'
        template[16] = f'    Na+         {get_concentration("sodium", day):.2e}  T\n'
        template[17] = f'    NO3-        {get_concentration("nitrate", day):.2e}  T\n'
        template[19] = f'    SiO2(aq)    {get_concentration("silicon", day):.2e}  T\n'
        template[20] = f'    SO4--       {get_concentration("sulfate", day):.2e}  T\n'
        template[21] = f'    SOC(aq)     {get_concentration("npoc", day):.2e}  T\n'
        template[22] = f'    Tracer      {1e-6:.2e}  T\n'

    def generate_transient_flow_conditions(self, upstream_file: str, downstream_file: str):
        """Generate transient flow condition files with CORRECTED DATUM calculations."""
        print("Generating transient flow conditions...")

        # Hydro BC files are in template_dir/hydro-bcs/
        hydro_bcs_dir = self.template_dir / 'hydro-bcs'
        upstream_path = hydro_bcs_dir / upstream_file
        downstream_path = hydro_bcs_dir / downstream_file

        upstream_data = pd.read_csv(upstream_path, sep='\t', header=2, index_col=False)
        downstream_data = pd.read_csv(downstream_path, sep='\t', header=2, index_col=False)

        bc_dir = self.output_dir / 'trans-top-bcs'
        bc_dir.mkdir(exist_ok=True)

        header = 'TIME_UNITS h\nDATA_UNITS m\n!h  x   y   z\n'

        for dx in range(self.nx):
            filename = bc_dir / f'top_hydro_bc_at_{dx}.txt'

            if filename.exists():
                filename.unlink()

            with open(filename, 'w') as f:
                f.write(header)

                for i in range(len(downstream_data['!h'])):
                    up_z = upstream_data['z'].iloc[i]
                    down_z = downstream_data['z'].iloc[i]

                    if self.nx == 1:
                        hx = up_z
                    else:
                        hx = up_z + (down_z - up_z) * (dx / (self.nx - 1))

                    f.write(f'{i:.4E}\t{0:.4E}\t{0:.4E}\t{hx:.4E}\n')

    def _get_grid_file(self) -> str:
        """Get the correct grid file path based on meander type.

        Grid files are shared across years and located in the simulations/
        directory (self.template_dir), not in year-specific subdirectories.
        """
        if self.meander == 'mzt':
            grid_file = self.template_dir / "xxgrid010-mz-cxc-top.h5"
        elif self.meander == 'mcp':
            grid_file = self.template_dir / "xxgrid010-mc-cxc-top.h5"
        else:
            raise ValueError(f"Unknown meander type: {self.meander}")

        return str(grid_file)

    def _replace_grid_file_placeholder(self, content: List[str]) -> List[str]:
        """Replace {{GRID_FILE}} placeholder with the full grid file path.

        This handles all FILE references in the template (STRATA, REGION blocks, etc.)
        and uses the full path which works on both Mac and Ubuntu via Path.home().
        """
        grid_file = self._get_grid_file()
        updated_content = []

        for line in content:
            if '{{GRID_FILE}}' in line:
                updated_content.append(line.replace('{{GRID_FILE}}', grid_file))
            else:
                updated_content.append(line)

        return updated_content

    def _update_grid_block(self, content: List[str]) -> List[str]:
        """Update the GRID block with the correct NXYZ for the meander type.

        MZT: NXYZ 1 108 26
        MCP: NXYZ 1 122 26
        """
        updated_content = []

        for line in content:
            if line.strip().startswith('NXYZ'):
                # Replace with correct ny value (self.nx is the number of cells in y)
                indent = len(line) - len(line.lstrip())
                updated_content.append(' ' * indent + f'NXYZ 1 {self.nx} 26\n')
            else:
                updated_content.append(line)

        return updated_content

    def _update_final_time(self, content: List[str], transient: bool = True) -> List[str]:
        """Update the FINAL_TIME in the TIME block based on simulation configuration.

        For transient simulations: uses self.final_time (hours)
        For spin-up simulations: keeps the template value (typically in years)
        """
        if not transient:
            # Don't modify spin-up files - they use years
            return content

        updated_content = []

        for line in content:
            if line.strip().startswith('FINAL_TIME') and 'h' in line:
                # Replace FINAL_TIME for transient simulations
                indent = len(line) - len(line.lstrip())
                updated_content.append(' ' * indent + f'FINAL_TIME {self.final_time}.d0 h\n')
            else:
                updated_content.append(line)

        return updated_content

    def _update_datum_files(self, content: List[str], upstream_file: str, downstream_file: str) -> List[str]:
        """Update the DATUM FILE references in upstream_bc and downstream_bc flow conditions.

        The template has hardcoded MZT file names that need to be replaced with the
        correct meander/year-specific files from the simulation configuration.
        """
        updated_content = []
        in_upstream_bc = False
        in_downstream_bc = False
        nesting_depth = 0

        for line in content:
            stripped = line.strip()

            # Track which flow condition block we're in
            if 'FLOW_CONDITION upstream_bc' in line:
                in_upstream_bc = True
                in_downstream_bc = False
                nesting_depth = 1
            elif 'FLOW_CONDITION downstream_bc' in line:
                in_upstream_bc = False
                in_downstream_bc = True
                nesting_depth = 1
            elif in_upstream_bc or in_downstream_bc:
                # Track nesting depth to know when we exit the FLOW_CONDITION block
                # Nested blocks (TYPE, MONOD, etc.) start with keywords and end with /
                if stripped == '/':
                    nesting_depth -= 1
                    if nesting_depth == 0:
                        in_upstream_bc = False
                        in_downstream_bc = False
                elif any(stripped.startswith(kw) for kw in ['TYPE', 'MONOD', 'INHIBITION']):
                    nesting_depth += 1

            # Replace DATUM FILE lines within the appropriate flow condition
            if 'DATUM FILE' in line and (in_upstream_bc or in_downstream_bc):
                indent = len(line) - len(line.lstrip())
                if in_upstream_bc:
                    updated_content.append(' ' * indent + f'DATUM FILE {upstream_file}\n')
                elif in_downstream_bc:
                    updated_content.append(' ' * indent + f'DATUM FILE {downstream_file}\n')
            else:
                updated_content.append(line)

        return updated_content

    def write_regions_block(self) -> str:
        """Generate regions block."""
        grid_file = self._get_grid_file()

        regions = []
        for ix in range(self.nx):
            regions.append(f"\nREGION top_bc_reg_{ix}\n  FILE {grid_file}\n/")
        return ''.join(regions)

    def write_flow_conditions_block(self, transient: bool = True,
                                  upstream_file: str = None, downstream_file: str = None) -> str:
        """Generate flow conditions block with CORRECTED DATUM calculations."""
        if transient and upstream_file and downstream_file:
            self.generate_transient_flow_conditions(upstream_file, downstream_file)

        flow_conditions = []

        for ix in range(self.nx):
            if self.nx == 1:
                hx = self.upstream_h
            else:
                hx = self.upstream_h + (self.downstream_h - self.upstream_h) * (ix / (self.nx - 1))

            if transient:
                condition = (f"\nFLOW_CONDITION top_river_bc_{ix}\n"
                           f"  TYPE\n    LIQUID_PRESSURE seepage\n  /\n"
                           f"  CYCLIC\n  DATUM FILE trans-top-bcs/top_hydro_bc_at_{ix}.txt\n"
                           f"  LIQUID_PRESSURE 101325.d0\n/")
            else:
                condition = (f"\nFLOW_CONDITION top_river_bc_{ix}\n"
                           f"  TYPE\n    LIQUID_PRESSURE seepage\n  /\n"
                           f"  CYCLIC\n  DATUM 0.d0 0.d0 {hx:.3f}d0\n"
                           f"  LIQUID_PRESSURE 101325.d0\n/")

            flow_conditions.append(condition)

        return ''.join(flow_conditions)

    def write_boundary_conditions_block(self) -> str:
        """Generate boundary conditions block."""
        bc_conditions = []

        for ix in range(self.nx):
            river_bc = (f'\nBOUNDARY_CONDITION top_river_{ix}\n'
                       f'  FLOW_CONDITION top_river_bc_{ix}\n'
                       f'  TRANSPORT_CONDITION from_river\n'
                       f'  REGION top_bc_reg_{ix}\n/')

            precip_bc = (f'\nBOUNDARY_CONDITION top_precip_{ix}\n'
                        f'  FLOW_CONDITION top_precip_bc\n'
                        f'  TRANSPORT_CONDITION from_precip\n'
                        f'  REGION top_bc_reg_{ix}\n/')

            bc_conditions.extend([river_bc, precip_bc])

        return ''.join(bc_conditions)

    def assemble_input_file(self, filename: str, transient: bool = True,
                          upstream_file: str = None, downstream_file: str = None):
        """Assemble complete PFLOTRAN input file."""
        print(f"Assembling {'transient' if transient else 'spin-up'} input file: {filename}")

        regions_block = self.write_regions_block()
        flow_conditions_block = self.write_flow_conditions_block(transient, upstream_file, downstream_file)

        if transient:
            river_chem, river_transport = self.write_chemistry_blocks('river')
            top_chem, top_transport = self.write_chemistry_blocks('top')
            bc_block = self.write_boundary_conditions_block()
            template_file = self.template_dir / 'TEMPLATE-pflotran.in'
        else:
            bc_block = self.write_boundary_conditions_block()
            template_file = self.template_dir / 'TEMPLATE-pflotran-spin.in'

        with open(template_file, 'r') as f:
            template_content = f.readlines()

        # Replace {{GRID_FILE}} placeholder with full path (works on Mac/Ubuntu)
        template_content = self._replace_grid_file_placeholder(template_content)

        # Update GRID block with correct NXYZ for this meander
        template_content = self._update_grid_block(template_content)

        # Update FINAL_TIME for transient simulations
        template_content = self._update_final_time(template_content, transient)

        # Update DATUM FILE references for upstream_bc and downstream_bc (transient only)
        if transient and upstream_file and downstream_file:
            template_content = self._update_datum_files(template_content, upstream_file, downstream_file)

        chunks = self._split_template_with_chemistry(template_content)

        output_file = self.output_dir / filename
        if output_file.exists():
            output_file.unlink()

        with open(output_file, 'w') as f:
            timestamp = self.generation_timestamp.strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"! Generated {timestamp} (Local Time)\n")
            f.write(f"! Output directory: {self.output_dir.absolute()}\n")
            f.write(f"! Meander: {self.meander.upper()}, Year: {self.year}\n\n")

            f.writelines(chunks[0])
            f.write(regions_block)
            f.writelines(chunks[1])
            f.write(flow_conditions_block)
            f.writelines(chunks[2])

            f.writelines(self.chemistry_block)

            f.writelines(chunks[3])

            if transient:
                f.writelines(river_chem)
                f.writelines(top_chem)
                f.writelines(chunks[4])
                f.writelines(river_transport)
                f.writelines(top_transport)
                f.writelines(chunks[5])
                f.write('\n\n')
                f.write(bc_block)
                f.writelines(chunks[6])
            else:
                f.write(bc_block)
                f.writelines(chunks[4])

        print(f"  File written: {output_file}")
        return filename

    def _split_template_with_chemistry(self, template_content: List[str]) -> List[List[str]]:
        """Split template file into chunks based on delimiters, accounting for chemistry placeholder."""
        chunks = []
        current_chunk = []
        in_chemistry_block = False
        chemistry_found = False

        for line in template_content:
            if "$%$%$% CHUNK DELIM %^%^%^" in line:
                chunks.append(current_chunk)
                current_chunk = []
            elif "#==================== CHEMISTRY ===================" in line:
                chunks.append(current_chunk)
                current_chunk = []
                in_chemistry_block = True
                chemistry_found = True
            elif in_chemistry_block and "#=========================== CONSTRAINTS ======================================" in line:
                in_chemistry_block = False
                current_chunk.append(line)
            elif not in_chemistry_block:
                current_chunk.append(line)

        if current_chunk:
            chunks.append(current_chunk)

        if not chemistry_found:
            chunks = []
            current_chunk = []
            for line in template_content:
                if "$%$%$% CHUNK DELIM %^%^%^" in line:
                    chunks.append(current_chunk)
                    current_chunk = []
                else:
                    current_chunk.append(line)
            if current_chunk:
                chunks.append(current_chunk)

        return chunks

    def generate_files(self, upstream_file: str = None, downstream_file: str = None) -> Tuple[str, str]:
        """Generate both spin-up and transient input files with meander and year in filenames."""
        timestamp = self.generation_timestamp.strftime("%Y-%m-%d_%H-%M-%S")
        year_suffix = self.year[-2:]

        transient_filename = f'pflotran-{self.meander}{year_suffix}_{timestamp}.in'
        self.assemble_input_file(transient_filename, True, upstream_file, downstream_file)

        spinup_filename = f'pflotran-{self.meander}{year_suffix}_{timestamp}_spin.in'
        self.assemble_input_file(spinup_filename, False)

        # Update transient file's RESTART FILENAME to match the spin checkpoint
        # PFLOTRAN automatically creates {basename}-restart.chk at simulation end
        transient_path = self.output_dir / transient_filename
        if transient_path.exists():
            with open(transient_path, 'r') as f:
                lines = f.readlines()

            for i, line in enumerate(lines):
                if 'FILENAME' in line and 'restart.chk' in line:
                    lines[i] = f"    FILENAME pflotran-{self.meander}{year_suffix}_{timestamp}_spin-restart.chk\n"
                    break

            with open(transient_path, 'w') as f:
                f.writelines(lines)

        return spinup_filename, transient_filename

    def create_run_log(self, spinup_file: str, transient_file: str,
                       upstream_file: str = None, downstream_file: str = None,
                       copied_files: List[str] = None) -> None:
        """Create a combined log file with arguments and run information."""
        log_file = self.output_dir / 'generation.log'

        with open(log_file, 'w') as f:
            f.write("PFLOTRAN Generator Log\n")
            f.write("=" * 50 + "\n\n")

            f.write(f"Generated: {self.generation_timestamp.strftime('%Y-%m-%d %H:%M:%S')} (Local Time)\n")
            f.write(f"Output Directory: {self.output_dir.absolute()}\n")
            f.write(f"Simulation Directory: {self.sim_dir.absolute()}\n")
            f.write(f"Template Directory: {self.template_dir.absolute()}\n\n")

            f.write("Arguments\n")
            f.write("-" * 50 + "\n")
            f.write(f"  year:            {self.year}\n")
            f.write(f"  meander:         {self.meander}\n")
            f.write(f"  nx:              {self.nx}\n")
            f.write(f"  upstream_h:      {self.upstream_h}\n")
            f.write(f"  downstream_h:    {self.downstream_h}\n")
            f.write(f"  final_time:      {self.final_time} h\n")
            f.write(f"  grid_file:       {self._get_grid_file()}\n")
            if upstream_file:
                f.write(f"  upstream_file:   {upstream_file}\n")
            if downstream_file:
                f.write(f"  downstream_file: {downstream_file}\n")
            f.write("\n")

            f.write("DATUM Calculation\n")
            f.write("-" * 50 + "\n")
            f.write(f"  First DATUM (ix=0): {self.upstream_h:.6f} m\n")
            if self.nx > 1:
                f.write(f"  Last DATUM (ix={self.nx-1}): {self.downstream_h:.6f} m\n")
                second_datum = self.upstream_h + (self.downstream_h - self.upstream_h) * (1 / (self.nx - 1))
                f.write(f"  Second DATUM (ix=1): {second_datum:.6f} m\n")
            f.write(f"  Linear interpolation between upstream and downstream\n\n")

            f.write("Created Files\n")
            f.write("-" * 50 + "\n")
            f.write(f"  {spinup_file}\n")
            f.write(f"  {transient_file}\n")
            f.write(f"  generation.log\n\n")

            f.write("Boundary Condition Files\n")
            f.write("-" * 50 + "\n")
            f.write("  river_chem.txt\n")
            f.write("  river_transport_constraint.txt\n")
            f.write("  top_chem.txt\n")
            f.write("  top_transport_constraint.txt\n")
            f.write("  trans-top-bcs/ (directory with BC files)\n\n")

            if copied_files:
                f.write("Copied Files\n")
                f.write("-" * 50 + "\n")
                for file in copied_files:
                    f.write(f"  {file}\n")

        print(f"Log saved: {log_file}")

    def copy_required_files(self, upstream_file: str = None, downstream_file: str = None) -> List[str]:
        """Copy required files to the output directory."""
        print("Copying required files to output directory...")

        files_to_copy = []

        hanford_path = self.sim_dir / 'hanford-cd.dat'
        if hanford_path.exists():
            files_to_copy.append((hanford_path, 'hanford-cd.dat'))
        else:
            print(f"  hanford-cd.dat not found in {self.sim_dir}")

        # Hydro BC files are in template_dir/hydro-bcs/
        hydro_bcs_dir = self.template_dir / 'hydro-bcs'

        if upstream_file:
            upstream_path = hydro_bcs_dir / upstream_file
            if upstream_path.exists():
                files_to_copy.append((upstream_path, upstream_file))
            else:
                print(f"  Upstream file not found: {upstream_path}")

        if downstream_file:
            downstream_path = hydro_bcs_dir / downstream_file
            if downstream_path.exists():
                files_to_copy.append((downstream_path, downstream_file))
            else:
                print(f"  Downstream file not found: {downstream_path}")

        template_files = [
            'TEMPLATE-constraint.txt',
            'TEMPLATE-chemistry.txt',
            'TEMPLATE-pflotran.in',
            'TEMPLATE-pflotran-spin.in'
        ]

        for template_file in template_files:
            template_path = self.template_dir / template_file
            if template_path.exists():
                files_to_copy.append((template_path, template_file))

        copied_files = []
        for source, dest_name in files_to_copy:
            try:
                dest_path = self.output_dir / dest_name
                shutil.copy2(source, dest_path)
                copied_files.append(dest_name)
                print(f"  Copied: {source.name} -> {dest_name}")
            except Exception as e:
                print(f"  Failed to copy {source}: {e}")

        if copied_files:
            print(f"  {len(copied_files)} files copied successfully")
        else:
            print("  No files were copied")

        return copied_files

    def test_datum_generation(self) -> None:
        """Test and validate DATUM generation logic."""
        print("\nTesting DATUM generation logic:")
        print(f"   nx = {self.nx}")
        print(f"   upstream_h = {self.upstream_h}")
        print(f"   downstream_h = {self.downstream_h}")

        test_datums = []
        for ix in range(self.nx):
            if self.nx == 1:
                hx = self.upstream_h
            else:
                hx = self.upstream_h + (self.downstream_h - self.upstream_h) * (ix / (self.nx - 1))
            test_datums.append(hx)

        print(f"   First DATUM (ix=0): {test_datums[0]:.6f} (should = {self.upstream_h})")
        if self.nx > 1:
            print(f"   Last DATUM (ix={self.nx-1}): {test_datums[-1]:.6f} (should = {self.downstream_h})")
            print(f"   Second DATUM (ix=1): {test_datums[1]:.6f}")

        assert abs(test_datums[0] - self.upstream_h) < 1e-10, "First DATUM incorrect!"
        if self.nx > 1:
            assert abs(test_datums[-1] - self.downstream_h) < 1e-10, "Last DATUM incorrect!"

        print("   DATUM generation test PASSED!")


def main():
    """Main function with command line interface."""

    parser = argparse.ArgumentParser(
        description='Generate PFLOTRAN input files for meander simulations',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument('--year', type=str, required=True,
                       help='Simulation year: 2018 or 2019')
    parser.add_argument('--meander', type=str, required=True,
                       help='Meander type: mcp or mzt')
    parser.add_argument('--test-datum', action='store_true',
                       help='Run DATUM generation test and exit')
    parser.add_argument('--keep-tuning-markers', action='store_true',
                       help='Keep $T markers in chemistry template (for tuning workflow)')

    args = parser.parse_args()

    # Validate inputs
    if args.year not in ['2018', '2019']:
        print(f"\nError: Invalid year '{args.year}'")
        print("Acceptable options: 2018, 2019")
        return 1

    if args.meander.lower() not in ['mcp', 'mzt']:
        print(f"\nError: Invalid meander '{args.meander}'")
        print("Acceptable options: mcp, mzt")
        return 1

    # Get configuration for this year/meander combination
    config_key = (args.year, args.meander.lower())
    config = SIMULATION_CONFIGS[config_key]

    # Determine directories
    script_dir = Path(__file__).parent  # simulations directory (contains templates)
    sim_dir = script_dir / config['subdir']  # subdirectory for this simulation
    template_dir = script_dir  # templates are in the simulations directory

    if not sim_dir.exists():
        print(f"\nError: Simulation directory not found: {sim_dir}")
        return 1

    print(f"\n{'='*60}")
    print(f"PFLOTRAN Generator v3.0 - Unified")
    print(f"{'='*60}")
    print(f"\nConfiguration for {args.meander.upper()} {args.year}:")
    print(f"  Template dir:    {template_dir}")
    print(f"  Simulation dir:  {sim_dir}")
    print(f"  nx:              {config['nx']}")
    print(f"  upstream_h:      {config['upstream_h']}")
    print(f"  downstream_h:    {config['downstream_h']}")
    print(f"  upstream_file:   {config['upstream_file']}")
    print(f"  downstream_file: {config['downstream_file']}")
    print(f"  final_time:      {config['final_time']} h")
    print(f"  grid_file:       {'xxgrid010-mz-cxc-top.h5' if args.meander.lower() == 'mzt' else 'xxgrid010-mc-cxc-top.h5'}")

    try:
        # Initialize generator
        # By default, strip $T markers for standalone runs
        # Use --keep-tuning-markers to preserve them for tuning workflow
        generator = PFLOTRANGenerator(
            year=args.year,
            meander=args.meander.lower(),
            nx=config['nx'],
            upstream_h=config['upstream_h'],
            downstream_h=config['downstream_h'],
            final_time=config['final_time'],
            sim_dir=sim_dir,
            template_dir=template_dir,
            strip_tuning_markers=not args.keep_tuning_markers
        )

        # Test DATUM generation if requested
        if args.test_datum:
            generator.test_datum_generation()
            print(f"\nDATUM test completed successfully!")
            return 0

        # Test DATUM generation before proceeding
        generator.test_datum_generation()

        # Generate files
        spinup_file, transient_file = generator.generate_files(
            config['upstream_file'],
            config['downstream_file']
        )

        # Copy required files to output directory
        copied_files = generator.copy_required_files(
            config['upstream_file'],
            config['downstream_file']
        )

        # Create combined generation log
        generator.create_run_log(
            spinup_file, transient_file,
            config['upstream_file'], config['downstream_file'],
            copied_files
        )

        print(f"\n{'='*60}")
        print(f"SUCCESS! Generated files:")
        print(f"{'='*60}")
        print(f"   Directory: {generator.output_dir.absolute()}")
        print(f"   Spin-up:   {spinup_file}")
        print(f"   Transient: {transient_file}")
        print(f"   Log:       generation.log")
        if copied_files:
            print(f"   Copied:    {len(copied_files)} files")

        print(f"\nFull path to spin-up file:")
        print(str(generator.output_dir / spinup_file))

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == '__main__':
    exit(main())
