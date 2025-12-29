#!/usr/bin/env python3
"""
PFLOTRAN Input File Generator for 1D Meander Simulations

This script generates PFLOTRAN input files for both spin-up and transient 1D simulations
using boundary condition data and template files. All outputs are saved to a nested
date-time directory structure: ./{YYYY-MM-DD}/{YYYY-MM-DD_HH-MM-SS}/

1D Simulation Features:
- Only upstream and downstream boundary conditions
- No top boundary conditions (river/precipitation)
- Simplified flow and transport conditions
- Focus on longitudinal flow direction

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
Date: 07.28.2025
Version: 3.2 - Updated formatting to match example structure and spacing
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


class PFLOTRAN1DGenerator:
    """Main class for generating PFLOTRAN 1D input files."""
    
    def __init__(self, year: str, ny: int = 108, upstream_h: float = 1.94, downstream_h: float = 1.66):
        self.year = year
        self.ny = ny
        self.upstream_h = upstream_h
        self.downstream_h = downstream_h
        self.bc_data = None
        self.chemistry_block = None
        
        # Create nested date-time output directory
        self.output_dir = self._create_output_directory()
        
        self.validate_inputs()
        self.load_chemistry_template()
    
    def _create_output_directory(self) -> Path:
        """Create nested date-time based output directory: ./{YYYY-MM-DD}/{YYYY-MM-DD_HH-MM-SS}/"""
        # Use local time instead of UTC for both directory naming and file generation
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        datetime_str = now.strftime("%Y-%m-%d_%H-%M-%S")
        
        # Create nested directory structure
        date_dir = Path(f"./{date_str}")
        output_dir = date_dir / datetime_str
        
        # Store the timestamp for consistent use in file headers
        self.generation_timestamp = now
        
        # Create directories if they don't exist
        output_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"📁 Output directory: {output_dir.absolute()}")
        print(f"🕐 Local timestamp: {now.strftime('%Y-%m-%d %H:%M:%S')}")
        return output_dir
    
    def validate_inputs(self):
        """Validate input parameters and required files."""
        if self.year not in YEAR_CONFIGS:
            raise ValueError(f"Year must be one of {list(YEAR_CONFIGS.keys())}")
        
        required_files = [
            'TEMPLATE-constraint.txt',
            'TEMPLATE-chemistry.txt',
            'TEMPLATE-pflotran-1d.in',      # Updated for 1D
            'TEMPLATE-pflotran-spin-1d.in'  # Updated for 1D
        ]
        
        for file in required_files:
            if not os.path.exists(file):
                raise FileNotFoundError(f"Required template file not found: {file}")
        
        if not os.path.exists('../bc_chem_data'):
            raise FileNotFoundError("Directory '../bc_chem_data' not found")
    
    def load_chemistry_template(self):
        """Load the chemistry template file."""
        print("Loading chemistry template...")
        try:
            with open('TEMPLATE-chemistry.txt', 'r') as f:
                self.chemistry_block = f.readlines()
            print(f"  ✓ Chemistry template loaded ({len(self.chemistry_block)} lines)")
        except Exception as e:
            raise FileNotFoundError(f"Failed to load chemistry template: {e}")
    
    def load_bc_data(self) -> Dict[str, pd.DataFrame]:
        """Load and process boundary condition data efficiently."""
        print("Loading boundary condition data...")
        print(f"Target year: {self.year}")
        year_config = YEAR_CONFIGS[self.year]
        print(f"Date range: {year_config['start']} to {year_config['end']}")
        
        bc_data = {}
        csv_files = [f for f in os.listdir('../bc_chem_data') if f.endswith('.csv')]
        
        if not csv_files:
            raise FileNotFoundError("No CSV files found in '../bc_chem_data'")
        
        for filename in csv_files:
            try:
                # Read file efficiently - remove row limit to get all data
                filepath = os.path.join('../bc_chem_data', filename)
                data = pd.read_csv(filepath)  # Read all data, not just first 1000 rows
                
                component = filename.split('.')[0].split('_')[-1]
                
                print(f"\n  Processing {component} from {filename}:")
                print(f"    Raw data shape: {data.shape}")
                
                unit = data.iloc[0, 1]
                print(f"    Unit: {unit}")
                
                # Process data
                df = data[1:].copy()
                print(f"    After removing header: {len(df)} rows")
                
                df['date'] = pd.to_datetime(df['date'], errors='coerce')
                print(f"    After date parsing: {len(df.dropna(subset=['date']))} valid dates")
                
                df[component] = pd.to_numeric(df[component], errors='coerce')
                print(f"    After numeric conversion: {len(df.dropna(subset=[component]))} valid values")
                
                # Remove invalid data
                df = df.dropna()
                print(f"    After removing NaN: {len(df)} rows")
                
                if len(df) > 0:
                    print(f"    Date range in data: {df['date'].min()} to {df['date'].max()}")
                
                # Calculate conversion factor
                conversion_factor = self._get_conversion_factor(component, unit)
                print(f"    Conversion factor: {conversion_factor}")
                
                # Interpolate data efficiently
                interpolated_data = self._interpolate_data(df, component, conversion_factor)
                print(f"    After interpolation: {len(interpolated_data)} rows")
                
                # Filter by year
                time_filtered = interpolated_data[
                    (interpolated_data['date'] >= year_config['start']) & 
                    (interpolated_data['date'] <= year_config['end'])
                ]
                print(f"    After year filtering: {len(time_filtered)} rows")
                
                if len(time_filtered) > 0:
                    print(f"    Final date range: {time_filtered['date'].min()} to {time_filtered['date'].max()}")
                else:
                    print(f"    ❌ No data remains after filtering for year {self.year}")
                    # Show what dates are available
                    if len(interpolated_data) > 0:
                        print(f"    Available date range: {interpolated_data['date'].min()} to {interpolated_data['date'].max()}")
                
                bc_data[component] = time_filtered
                print(f"  ✓ {component} loaded ({len(time_filtered)} data points)")
                
            except Exception as e:
                print(f"  ✗ Failed to load {component}: {e}")
                import traceback
                traceback.print_exc()
        
        # Post-process nitrate data
        if 'nitrate' in bc_data:
            self._fix_nitrate_data(bc_data['nitrate'])
        
        # Only validate if we have insufficient data after trying to load everything
        components_with_no_data = [comp for comp, df in bc_data.items() if len(df) == 0]
        if len(components_with_no_data) > 0:
            print(f"\n⚠️  Components with no data after filtering: {components_with_no_data}")
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
        
        # Default fallback values (in M units, except pH)
        fallback_values = {
            'pH': 7.0,           # pH units
            'aluminum': 1e-9,    # M
            'calcium': 1e-6,     # M  
            'chloride': 1e-6,    # M
            'dic': 1e-6,         # M
            'potassium': 1e-7,   # M
            'magnesium': 1e-7,   # M
            'sodium': 1e-6,      # M
            'nitrate': 1e-8,     # M
            'silicon': 1e-8,     # M
            'sulfate': 1e-7,     # M
            'npoc': 1e-9         # M
        }
        
        # Get the expected number of days for the simulation
        year_config = YEAR_CONFIGS[self.year]
        total_days = int((year_config['end'] - year_config['start']).total_seconds() / 3600 / 24)
        
        # Check each required component
        for component in required_components:
            if component not in bc_data or len(bc_data[component]) == 0:
                print(f"  ⚠️  No data for {component}, using fallback value: {fallback_values[component]}")
                
                # Create fallback DataFrame with constant values
                dates = pd.date_range(year_config['start'], year_config['end'], freq='D')
                fallback_df = pd.DataFrame({
                    'date': dates,
                    f'{component}_M': [fallback_values[component]] * len(dates)
                })
                
                bc_data[component] = fallback_df
            
            elif len(bc_data[component]) < total_days * 0.5:  # Less than 50% coverage
                print(f"  ⚠️  Insufficient data for {component} ({len(bc_data[component])} points), " + 
                      f"extending with fallback value: {fallback_values[component]}")
                
                # Extend existing data with fallback values
                existing_df = bc_data[component]
                if len(existing_df) > 0:
                    # Use last available value or fallback
                    last_value = existing_df.iloc[-1, 1] if len(existing_df) > 0 else fallback_values[component]
                else:
                    last_value = fallback_values[component]
                
                # Create extended DataFrame
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
            
            # Check if gap > 24 hours
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
        """Fix negative nitrate values."""
        column = f'nitrate_M'
        for i in range(1, len(nitrate_df)):
            if nitrate_df[column].iloc[i] <= 0.0:
                nitrate_df[column].iloc[i] = nitrate_df[column].iloc[i-1]
    
    def write_chemistry_blocks(self, block_type: str = 'upstream') -> Tuple[List[str], List[str]]:
        """Write chemistry and transport constraint blocks for 1D simulation."""
        print(f"Writing {block_type} chemistry blocks...")
        
        # Clean up existing files in output directory
        chem_file = self.output_dir / f'{block_type}_chem.txt'
        transport_file = self.output_dir / f'{block_type}_transport_constraint.txt'
        
        for file in [chem_file, transport_file]:
            if file.exists():
                file.unlink()
        
        # Load template
        with open('TEMPLATE-constraint.txt', 'r') as f:
            template = f.readlines()
        
        if not self.bc_data:
            self.load_bc_data()
        
        # Calculate simulation days
        year_config = YEAR_CONFIGS[self.year]
        diff_days = int((year_config['end'] - year_config['start']).total_seconds() / 3600 / 24)
        
        # Write chemistry constraints
        for day in range(diff_days - 1):
            template[0] = f'CONSTRAINT  from_{block_type}_conc_{day*24}\n'
            
            # Update concentrations
            self._update_template_concentrations(template, day)
            
            with open(chem_file, 'a') as f:
                f.writelines(template)
        
        # Write transport conditions - 1D specific
        transport_type = 'dirichlet_zero_gradient'
        
        start_string = (f'TRANSPORT_CONDITION  from_{block_type}\n'
                       f'  TIME_UNITS h\n'
                       f'  TYPE {transport_type}\n'
                       f'    CONSTRAINT_LIST\n')
        
        with open(transport_file, 'a') as f:
            f.write(start_string)
            
            for day in range(diff_days - 1):
                f.write(f'      {day*24}.d0  from_{block_type}_conc_{day*24}\n')
            
            f.write('    /\n')
            f.write('  END\n')
        
        # Read and return file contents
        with open(chem_file, 'r') as f:
            chem_blocks = f.readlines()
        
        with open(transport_file, 'r') as f:
            transport_blocks = f.readlines()
        
        return chem_blocks, transport_blocks
    
    def write_static_chemistry_blocks(self, block_type: str = 'river') -> Tuple[List[str], List[str]]:
        """Write static chemistry and transport constraint blocks for spin-up simulation."""
        print(f"Writing static {block_type} chemistry blocks for spin-up...")
        
        # Clean up existing files in output directory
        chem_file = self.output_dir / f'{block_type}_chem.txt'
        transport_file = self.output_dir / f'{block_type}_transport_constraint.txt'
        
        for file in [chem_file, transport_file]:
            if file.exists():
                file.unlink()
        
        # Load template
        with open('TEMPLATE-constraint.txt', 'r') as f:
            template = f.readlines()
        
        if not self.bc_data:
            self.load_bc_data()
        
        # Write single static chemistry constraint (use first day's data)
        template[0] = f'CONSTRAINT  from_{block_type}_conc\n'
        
        # Update concentrations with first day's values
        self._update_template_concentrations(template, 0)
        
        with open(chem_file, 'w') as f:
            f.writelines(template)
        
        # Write static transport condition
        transport_content = [
            f'TRANSPORT_CONDITION  from_{block_type}\n',
            f'  TYPE dirichlet_zero_gradient\n',
            f'    CONSTRAINT_LIST\n',
            f'      0.d0 from_{block_type}_conc\n',
            f'    /\n',
            f'  END\n'
        ]
        
        with open(transport_file, 'w') as f:
            f.writelines(transport_content)
        
        # Read and return file contents
        with open(chem_file, 'r') as f:
            chem_blocks = f.readlines()
        
        with open(transport_file, 'r') as f:
            transport_blocks = f.readlines()
        
        return chem_blocks, transport_blocks
    
    def _update_template_concentrations(self, template: List[str], day: int):
        """Update template with concentration values for given day."""
        bc = self.bc_data
        
        # Safely access data with bounds checking
        def get_concentration(component: str, day_index: int) -> float:
            """Safely get concentration value for a given day."""
            if component not in bc or len(bc[component]) == 0:
                return 1e-9  # Fallback concentration
            
            # Ensure day_index is within bounds
            max_index = len(bc[component]) - 1
            safe_index = min(day_index, max_index)
            
            try:
                return bc[component].iloc[safe_index, 1]
            except (IndexError, KeyError):
                return 1e-9  # Fallback if still fails
        
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
    
    def write_flow_conditions_block_1d(self, transient: bool = True) -> str:
        """Generate 1D flow conditions block - simplified for upstream/downstream only."""
        print("Generating 1D flow conditions...")
        
        flow_conditions = []
        
        if transient:
            # For transient simulations, use DATUM FILE references
            # Find existing hydraulic data files using glob patterns
            upstream_files = glob.glob(f"hydro_us_{self.year}_*.txt")
            downstream_files = glob.glob(f"hydro_ds_{self.year}_*.txt")
            
            if upstream_files:
                upstream_hydro_file = upstream_files[0]  # Use first match
                print(f"  ✓ Found upstream hydraulic file: {upstream_hydro_file}")
            else:
                # Fallback to expected naming convention
                year_config = YEAR_CONFIGS[self.year]
                start_date = year_config['start']
                end_date = year_config['end']
                start_str = f"{start_date.month}-{start_date.day}"
                end_str = f"{end_date.month}-{end_date.day}"
                upstream_hydro_file = f"hydro_us_{self.year}_{start_str}_{end_str}-MZT.txt"
                print(f"  ⚠️  No upstream hydraulic file found, using expected name: {upstream_hydro_file}")
            
            if downstream_files:
                downstream_hydro_file = downstream_files[0]  # Use first match
                print(f"  ✓ Found downstream hydraulic file: {downstream_hydro_file}")
            else:
                # Fallback to expected naming convention
                year_config = YEAR_CONFIGS[self.year]
                start_date = year_config['start']
                end_date = year_config['end']
                start_str = f"{start_date.month}-{start_date.day}"
                end_str = f"{end_date.month}-{end_date.day}"
                downstream_hydro_file = f"hydro_ds_{self.year}_{start_str}_{end_str}-MZT.txt"
                print(f"  ⚠️  No downstream hydraulic file found, using expected name: {downstream_hydro_file}")
            
            # Upstream boundary condition with file reference
            upstream_condition = (f"FLOW_CONDITION upstream_bc\n"
                                f"  TYPE\n"
                                f"    LIQUID_PRESSURE seepage \n"
                                f"  /\n"
                                f"  CYCLIC\n"
                                f"  DATUM FILE {upstream_hydro_file}\n"
                                f"  LIQUID_PRESSURE 101325.d0\n"
                                f"/")
            
            # Downstream boundary condition with file reference  
            downstream_condition = (f"FLOW_CONDITION downstream_bc\n"
                                  f"  TYPE\n"
                                  f"    LIQUID_PRESSURE seepage\n"
                                  f"  /\n"
                                  f"  CYCLIC\n"
                                  f"  DATUM FILE {downstream_hydro_file}\n"
                                  f"  LIQUID_PRESSURE 101325.d0 \n"
                                  f"/")
        else:
            # For spin-up simulations, use static DATUM values
            upstream_condition = (f"FLOW_CONDITION upstream_bc\n"
                                f"  TYPE\n"
                                f"    LIQUID_PRESSURE seepage\n"
                                f"  /\n"
                                f"  CYCLIC\n"
                                f"  DATUM 0.d0 0.d0 {self.upstream_h:.3f}d0\n"
                                f"  LIQUID_PRESSURE 101325.d0\n"
                                f"/")
            
            downstream_condition = (f"FLOW_CONDITION downstream_bc\n"
                                  f"  TYPE\n"
                                  f"    LIQUID_PRESSURE seepage\n"
                                  f"  /\n"
                                  f"  CYCLIC\n"
                                  f"  DATUM 0.d0 0.d0 {self.downstream_h:.3f}d0\n"
                                  f"  LIQUID_PRESSURE 101325.d0\n"
                                  f"/")
        
        flow_conditions.extend([upstream_condition, "\n\n", downstream_condition])
        
        return ''.join(flow_conditions)
    
    def write_regions_block_1d(self) -> str:
        """Generate 1D regions block - discretized along y-direction with 0.5 m spacing."""
        regions = []
        
        # Upstream region - first cell face (y = 0) 
        upstream_region = (f"REGION upstream_bc_reg\n"
                          f"  COORDINATES\n"
                          f"    0.d0 0.0d0 0.d0\n"
                          f"    1.d0 0.0d0 1.d0\n"
                          f"  /\n"
                          f"  FACE SOUTH\n"
                          f"/")
        
        # Downstream region - last cell face (y = ny*0.5)
        downstream_y = self.ny * 0.5
        downstream_region = (f"REGION downstream_bc_reg\n"
                            f"  COORDINATES\n"
                            f"    0.d0 {downstream_y:.1f}d0 0.d0\n"
                            f"    1.d0 {downstream_y:.1f}d0 1.d0\n"
                            f"  /\n"
                            f"  FACE NORTH\n"
                            f"/")
        
        regions.extend([upstream_region, "\n\n", downstream_region])
        
        return ''.join(regions)
    
    def write_boundary_conditions_block_1d(self) -> str:
        """Generate 1D boundary conditions block - only upstream/downstream."""
        bc_conditions = []
        
        # Upstream boundary condition
        upstream_bc = (f'BOUNDARY_CONDITION river_upstream\n'
                      f'  FLOW_CONDITION upstream_bc\n'
                      f'  TRANSPORT_CONDITION from_river\n'
                      f'  REGION upstream_bc_reg\n'
                      f'/')
        
        downstream_bc = (f'BOUNDARY_CONDITION river_downstream\n'
                        f'  FLOW_CONDITION downstream_bc\n'
                        f'  TRANSPORT_CONDITION from_river\n'
                        f'  REGION downstream_bc_reg\n'
                        f'/')
        
        bc_conditions.extend([upstream_bc, '\n\n', downstream_bc])
        
        return ''.join(bc_conditions)
    
    def assemble_input_file(self, filename: str, transient: bool = True):
        """Assemble complete PFLOTRAN 1D input file."""
        print(f"Assembling {'transient' if transient else 'spin-up'} 1D input file: {filename}")
        
        # Generate all blocks
        regions_block = self.write_regions_block_1d()
        flow_conditions_block = self.write_flow_conditions_block_1d(transient)
        
        if transient:
            river_chem, river_transport = self.write_chemistry_blocks('river')
            bc_block = self.write_boundary_conditions_block_1d()
            template_file = 'TEMPLATE-pflotran-1d.in'
        else:
            # For spin-up, generate static river chemistry constraint
            river_chem, river_transport = self.write_static_chemistry_blocks('river')
            bc_block = self.write_boundary_conditions_block_1d()
            template_file = 'TEMPLATE-pflotran-spin-1d.in'
        
        # Read template and split into chunks
        with open(template_file, 'r') as f:
            template_content = f.readlines()
        
        chunks = self._split_template_with_chemistry(template_content)
        
        # Write final file to output directory
        output_file = self.output_dir / filename
        if output_file.exists():
            output_file.unlink()
        
        if transient:
            with open(output_file, 'w') as f:
                # Header - use the stored timestamp for consistency
                timestamp = self.generation_timestamp.strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"! Generated {timestamp} (Local Time) - 1D Simulation\n")
                f.write(f"! Output directory: {self.output_dir.absolute()}\n\n")
                
                # Assemble file with proper spacing matching the example
                f.writelines(chunks[0])  # Up to regions
                f.write('\n')
                f.write(regions_block)
                f.write('\n\n')
                f.writelines(chunks[1])  # Flow conditions section
                f.write('\n')
                f.write(flow_conditions_block)
                f.write('\n\n')
                f.writelines(chunks[2])  # Chemistry section placeholder
                
                # Insert CHEMISTRY block from template
                f.write('\n')
                f.writelines(self.chemistry_block)
                f.write('\n')
                
                f.writelines(chunks[3])  # initial_gravel constraint from template
                
                # Add river chemistry constraints
                f.writelines(river_chem)
                f.write('\n')
                
                # Write TRANSPORT CONDITIONS section
                f.writelines(chunks[4])  # initial_all transport condition from template
                
                # Add river transport condition
                f.write('\n')
                f.writelines(river_transport)
                f.write('\n')
                
                # Write boundary conditions section
                f.write('\n')
                f.write('  #======================BOUNDARY CONDITION==========================\n')
                f.write(bc_block)
                f.write('\n')
                
                # Write initial condition section
                f.write('\n')
                f.write('  #========================INITIAL CONDITION==========================\n')
                f.write('  INITIAL_CONDITION initial\n')
                f.write('    FLOW_CONDITION initial\n')
                f.write('    TRANSPORT_CONDITION initial_all\n')
                f.write('    REGION all\n')
                f.write('  /\n\n')
                
                # End subsurface
                f.write('END_SUBSURFACE\n')

        else:
            with open(output_file, 'w') as f:
                # Header - use the stored timestamp for consistency
                timestamp = self.generation_timestamp.strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"! Generated {timestamp} (Local Time) - 1D Simulation\n")
                f.write(f"! Output directory: {self.output_dir.absolute()}\n\n")
                
                # Assemble file with proper spacing matching the example
                f.writelines(chunks[0])  # Up to regions
                f.write('\n')
                f.write(regions_block)
                f.write('\n\n')
                f.writelines(chunks[1])  # Flow conditions section
                f.write('\n')
                f.write(flow_conditions_block)
                f.write('\n\n')
                f.writelines(chunks[2])  # Chemistry section placeholder
                
                # Insert CHEMISTRY block from template
                f.write('\n')
                f.writelines(self.chemistry_block)
                f.write('\n')
                
                f.writelines(chunks[3])  # initial_gravel constraint from template

        print(f"  ✓ File written: {output_file}")
        return filename
    
    def _split_template_with_chemistry(self, template_content: List[str]) -> List[List[str]]:
        """Split template file into chunks based on delimiters."""
        chunks = []
        current_chunk = []
        
        for line in template_content:
            if "$%$%$% CHUNK DELIM %^%^%^" in line:
                chunks.append(current_chunk)
                current_chunk = []
            else:
                current_chunk.append(line)
        
        # Add final chunk
        if current_chunk:
            chunks.append(current_chunk)
        
        return chunks
    
    def generate_files(self) -> Tuple[str, str]:
        """Generate both spin-up and transient 1D input files."""
        # Use the same timestamp for both directory creation and file naming
        timestamp = self.generation_timestamp.strftime("%Y-%m-%d_%H-%M-%S")
        
        # Generate transient file
        transient_filename = f'pflotran-1d_{timestamp}.in'
        self.assemble_input_file(transient_filename, True)
        
        # Generate spin-up file with 'spin' suffix
        spinup_filename = f'pflotran-1d_{timestamp}_spin.in'
        self.assemble_input_file(spinup_filename, False)
        
        # Update restart file reference in transient file
        transient_path = self.output_dir / transient_filename
        if transient_path.exists():
            with open(transient_path, 'r') as f:
                lines = f.readlines()
            
            # Find and update restart file line to reference spin file
            for i, line in enumerate(lines):
                if 'FILENAME' in line and 'restart.chk' in line:
                    lines[i] = f"    FILENAME pflotran-1d_{timestamp}_spin-restart.chk\n"
                    break
            
            with open(transient_path, 'w') as f:
                f.writelines(lines)
        
        return spinup_filename, transient_filename
    
    def create_run_summary(self, spinup_file: str, transient_file: str, copied_files: List[str] = None) -> None:
        """Create a summary file with run information."""
        summary_file = self.output_dir / 'run_summary.txt'
        
        with open(summary_file, 'w') as f:
            f.write("PFLOTRAN 1D Input File Generation Summary\n")
            f.write("=" * 45 + "\n\n")
            f.write(f"Generation Date: {self.generation_timestamp.strftime('%Y-%m-%d %H:%M:%S')} (Local Time)\n")
            f.write(f"Output Directory: {self.output_dir.absolute()}\n\n")
            
            f.write("1D Simulation Configuration:\n")
            f.write(f"  Simulation Year: {self.year}\n")
            f.write(f"  Grid Cells (ny): {self.ny}\n")
            f.write(f"  Y-direction discretization: 0.5 m per cell\n")
            f.write(f"  Total transect length: {self.ny * 0.5:.1f} m\n")
            f.write(f"  Upstream Head: {self.upstream_h} m\n")
            f.write(f"  Downstream Head: {self.downstream_h} m\n\n")
            
            f.write("1D Simulation Features:\n")
            f.write("  ✓ Only upstream/downstream boundary conditions\n")
            f.write("  ✓ No top boundary conditions (no river/precipitation)\n")
            f.write("  ✓ Discretized along y-direction (0.5 m per cell)\n")
            f.write("  ✓ Flow in y-direction (upstream to downstream)\n")
            f.write("  ✓ Hydraulic head boundary conditions with DATUM\n")
            f.write("  ✓ Grid defined in input file (no external grid file)\n")
            f.write("  ✓ Transport conditions for both spin-up and transient\n")
            f.write("  ✓ Formatting matches example structure and spacing\n")
            f.write("  ✓ Proper constraint and transport condition generation\n\n")
            
            f.write("Generated Files:\n")
            f.write(f"  Spin-up: {spinup_file}\n")
            f.write(f"  Transient: {transient_file}\n")
            
            f.write("\nBoundary Condition Files:\n")
            f.write("  river_chem.txt (generated for both spin-up and transient)\n")
            f.write("  river_transport_constraint.txt (generated for both spin-up and transient)\n")
            f.write("  Note: Spin-up uses static constraints, transient uses time-varying constraints\n")
            
            f.write("\n1D Template Files Used:\n")
            f.write("  TEMPLATE-constraint.txt\n")
            f.write("  TEMPLATE-chemistry.txt\n")
            f.write("  TEMPLATE-pflotran-1d.in\n")
            f.write("  TEMPLATE-pflotran-spin-1d.in\n")
            
            if copied_files:
                f.write(f"\nCopied Reference Files:\n")
                for file in copied_files:
                    f.write(f"  {file}\n")
        
        print(f"📋 Run summary saved: {summary_file}")
    
    def copy_required_files(self) -> None:
        """Copy required files to the output directory."""
        print("📋 Copying required files to output directory...")
        
        files_to_copy = []
        
        # Always copy hanford-cd.dat if it exists
        if os.path.exists('hanford-cd.dat'):
            files_to_copy.append(('hanford-cd.dat', 'hanford-cd.dat'))
        else:
            print("  ⚠️  hanford-cd.dat not found in current directory")
        
        # Copy hydraulic data files for transient simulations
        year_config = YEAR_CONFIGS[self.year]
        start_date = year_config['start']
        end_date = year_config['end']
        
        # Format dates for filename - check multiple possible formats
        start_str = f"{start_date.month}-{start_date.day}"
        end_str = f"{end_date.month}-{end_date.day}"
        
        # Possible hydraulic file patterns to look for
        hydro_patterns = [
            f"hydro_us_{self.year}_{start_str}_{end_str}-MZT.txt",
            f"hydro_ds_{self.year}_{start_str}_{end_str}-MZT.txt",
            f"hydro_us_{self.year}_*.txt",  # Wildcard pattern
            f"hydro_ds_{self.year}_*.txt"   # Wildcard pattern
        ]
        
        # Look for hydraulic files using glob for wildcard patterns
        for pattern in hydro_patterns:
            if '*' in pattern:
                # Use glob for wildcard patterns
                matches = glob.glob(pattern)
                for match in matches:
                    if os.path.exists(match):
                        files_to_copy.append((match, os.path.basename(match)))
                        print(f"  ✓ Found hydraulic file: {match}")
            else:
                # Direct file check
                if os.path.exists(pattern):
                    files_to_copy.append((pattern, pattern))
                    print(f"  ✓ Found hydraulic file: {pattern}")
        
        # Copy 1D template files for reference
        template_files = [
            'TEMPLATE-constraint.txt',
            'TEMPLATE-chemistry.txt',
            'TEMPLATE-pflotran-1d.in',     # 1D templates
            'TEMPLATE-pflotran-spin-1d.in'  # 1D templates
        ]
        
        for template_file in template_files:
            if os.path.exists(template_file):
                files_to_copy.append((template_file, template_file))
        
        # Perform the copying
        copied_files = []
        for source, dest_name in files_to_copy:
            try:
                dest_path = self.output_dir / dest_name
                shutil.copy2(source, dest_path)
                copied_files.append(dest_name)
                print(f"  ✓ Copied: {source} -> {dest_name}")
            except Exception as e:
                print(f"  ✗ Failed to copy {source}: {e}")
        
        if copied_files:
            print(f"  📁 {len(copied_files)} files copied successfully")
        else:
            print("  ⚠️  No files were copied")
        
        return copied_files


def main():
    """Main function with command line interface."""
    parser = argparse.ArgumentParser(
        description='Generate PFLOTRAN 1D input files for meander simulations',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument('--year', choices=['2018', '2019'], default='2019',
                       help='Simulation year (default: 2019)')
    parser.add_argument('--ny', type=int, default=108,
                       help='Number of grid cells in y-direction (default: 108)')
    parser.add_argument('--upstream_h', type=float, default=1.94,
                       help='Upstream hydraulic head (default: 1.94)')
    parser.add_argument('--downstream_h', type=float, default=1.66,
                       help='Downstream hydraulic head (default: 1.66)')
    
    args = parser.parse_args()
    
    try:
        # Initialize 1D generator
        generator = PFLOTRAN1DGenerator(
            year=args.year,
            ny=args.ny,
            upstream_h=args.upstream_h,
            downstream_h=args.downstream_h
        )
        
        # Generate files
        spinup_file, transient_file = generator.generate_files()
        
        # Copy required files to output directory
        copied_files = generator.copy_required_files()
        
        # Create run summary
        generator.create_run_summary(
            spinup_file, transient_file, copied_files
        )
        
        print(f"\n✅ SUCCESS! Generated 1D files in nested directory structure:")
        print(f"   📁 Directory: {generator.output_dir.absolute()}")
        print(f"   🔧 Spin-up: {spinup_file}")
        print(f"   ⚡ Transient: {transient_file}")
        print(f"   📋 Summary: run_summary.txt")
        if copied_files:
            print(f"   📄 Copied files: {', '.join(copied_files)}")
        print(f"\n🎯 Key Features of 1D Version:")
        print(f"   ✅ Only upstream/downstream boundary conditions")
        print(f"   ✅ No top boundary conditions (river/precipitation)")
        print(f"   ✅ Discretized along y-direction (0.5 m per cell)")
        print(f"   ✅ Flow in y-direction (upstream to downstream)")
        print(f"   ✅ Uses 1D template files: TEMPLATE-pflotran-1d.in, TEMPLATE-pflotran-spin-1d.in")
        print(f"   ✅ Hydraulic head boundary conditions with DATUM")
        print(f"   ✅ Grid defined in input file (no external grid file)")
        print(f"   ✅ Transport conditions for both spin-up and transient")
        print(f"   ✅ Formatting matches example structure and spacing")
        print(f"   ✅ Proper constraint and transport condition generation")
        print(f"   ✅ Nested directory structure: ./{datetime.now().strftime('%Y-%m-%d')}/{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}/")
        
        # For backward compatibility, print the full path to spin-up file
        print(f"\n📄 Full path to spin-up file:")
        print(str(generator.output_dir / spinup_file))
        
        # Set environment variable
        os.environ["FILE"] = str(generator.output_dir / spinup_file)

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == '__main__':
    exit(main())