#!/usr/bin/env python3
"""
PFLOTRAN Input File Generator for Meander Simulations

This script generates PFLOTRAN input files for both spin-up and transient simulations
using boundary condition data and template files. All outputs are saved to a nested
date-time directory structure: ./{YYYY-MM-DD}/{YYYY-MM-DD_HH-MM-SS}/

Requirements:
- pandas
- datetime
- os

File Structure Required:
├── chem-bcs/           # Directory with CSV boundary condition files
├── TEMPLATE-constraint.txt # Chemistry constraint template
├── TEMPLATE-chemistry.txt  # Chemistry block template (NEW)
├── TEMPLATE-pflotran.in    # Main PFLOTRAN template 
├── TEMPLATE-pflotran-spin.in # Spin-up template
├── hydro_us_*.txt         # Upstream hydrological data
└── hydro_ds_*.txt         # Downstream hydrological data

Usage:
    python pflotran_generator.py [--year YEAR] [--meander MEANDER]
    
Example:
    python pflotran_generator.py --year 2019 --meander mzt 

Author: Christian Dewey
Date: 07.22.2025
Version: 2.2 - Added --meander argument for mcp/mzt support with updated file naming
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


class PFLOTRANGenerator:
    """Main class for generating PFLOTRAN input files with corrected DATUM calculations."""
    
    def __init__(self, year: str, meander: str, nx: int = 108, upstream_h: float = 1.94, downstream_h: float = 1.66):
        self.year = year
        self.meander = meander.lower()
        self.nx = nx
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
        
        if self.meander not in ['mcp', 'mzt']:
            raise ValueError(f"Meander must be one of ['mcp', 'mzt'], got: {self.meander}")
        
        required_files = [
            'TEMPLATE-constraint.txt',
            'TEMPLATE-chemistry.txt',  # NEW: Chemistry template
            'TEMPLATE-pflotran.in', 
            'TEMPLATE-pflotran-spin.in'
        ]
        
        for file in required_files:
            if not os.path.exists(file):
                raise FileNotFoundError(f"Required template file not found: {file}")
        
        if not os.path.exists('../chem-bcs'):
            raise FileNotFoundError("Directory '../chem-bcs' not found")
    
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
        print(f"Meander: {self.meander.upper()}")
        year_config = YEAR_CONFIGS[self.year]
        print(f"Date range: {year_config['start']} to {year_config['end']}")
        
        bc_data = {}
        csv_files = [f for f in os.listdir('../chem-bcs') if f.endswith('.csv')]
        
        if not csv_files:
            raise FileNotFoundError("No CSV files found in '../chem-bcs'")
        
        for filename in csv_files:
            try:
                # Read file efficiently - remove row limit to get all data
                filepath = os.path.join('../chem-bcs', filename)
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
    
    def write_chemistry_blocks(self, block_type: str = 'river') -> Tuple[List[str], List[str]]:
        """Write chemistry and transport constraint blocks."""
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
            template[0] = f'\nCONSTRAINT  from_{block_type}_conc_{day*24}\n'
            
            # Update concentrations
            self._update_template_concentrations(template, day)
            
            with open(chem_file, 'a') as f:
                f.writelines(template)
        
        # Write transport conditions
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
    
    def generate_transient_flow_conditions(self, upstream_file: str, downstream_file: str):
        """Generate transient flow condition files with CORRECTED DATUM calculations."""
        print("Generating transient flow conditions...")
        
        upstream_data = pd.read_csv(upstream_file, sep='\t', header=2, index_col=False)
        downstream_data = pd.read_csv(downstream_file, sep='\t', header=2, index_col=False)
        
        # Create subdirectory for boundary condition files
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
                    
                    # CORRECTED DATUM CALCULATION:
                    # Linear interpolation between upstream and downstream values
                    # dx=0: use upstream value, dx=nx-1: use downstream value
                    if self.nx == 1:
                        hx = up_z  # Special case for single cell
                    else:
                        hx = up_z + (down_z - up_z) * (dx / (self.nx - 1))
                    
                    f.write(f'{i:.4E}\t{0:.4E}\t{0:.4E}\t{hx:.4E}\n')
    
    def write_regions_block(self) -> str:
        """Generate regions block."""
        # Choose grid file based on meander type
        if self.meander == 'mzt':
            grid_file = "../../xxgrid010-mz-cxc-top.h5"
        elif self.meander == 'mcp':
            grid_file = "../../xxgrid010-mc-cxc-top.h5"
        else:
            raise ValueError(f"Unknown meander type: {self.meander}")
        
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
        
        # CORRECTED DATUM CALCULATION:
        # - upstream_h should be the FIRST DATUM value (ix=0)
        # - downstream_h should be the LAST DATUM value (ix=nx-1) 
        # - Linear interpolation between them for intermediate values
        
        for ix in range(self.nx):
            if self.nx == 1:
                # Special case: only one cell, use upstream value
                hx = self.upstream_h
            else:
                # Linear interpolation: hx = upstream_h + (downstream_h - upstream_h) * (ix / (nx-1))
                # When ix = 0: hx = upstream_h (first DATUM)
                # When ix = nx-1: hx = downstream_h (last DATUM)
                hx = self.upstream_h + (self.downstream_h - self.upstream_h) * (ix / (self.nx - 1))
            
            if transient:
                # Use relative path for boundary condition files
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
        
        # Generate all blocks
        regions_block = self.write_regions_block()
        flow_conditions_block = self.write_flow_conditions_block(transient, upstream_file, downstream_file)
        
        if transient:
            river_chem, river_transport = self.write_chemistry_blocks('river')
            top_chem, top_transport = self.write_chemistry_blocks('top')
            bc_block = self.write_boundary_conditions_block()
            template_file = 'TEMPLATE-pflotran.in'
        else:
            bc_block = self.write_boundary_conditions_block()
            template_file = 'TEMPLATE-pflotran-spin.in'
        
        # Read template and split into chunks
        with open(template_file, 'r') as f:
            template_content = f.readlines()
        
        chunks = self._split_template_with_chemistry(template_content)
        
        # Write final file to output directory
        output_file = self.output_dir / filename
        if output_file.exists():
            output_file.unlink()
        
        with open(output_file, 'w') as f:
            # Header - use the stored timestamp for consistency
            timestamp = self.generation_timestamp.strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"! Generated {timestamp} (Local Time)\n")
            f.write(f"! Output directory: {self.output_dir.absolute()}\n")
            f.write(f"! Meander: {self.meander.upper()}, Year: {self.year}\n\n")
            
            # Assemble file
            f.writelines(chunks[0])
            f.write(regions_block)
            f.writelines(chunks[1])
            f.write(flow_conditions_block)
            f.writelines(chunks[2])
            
            # Insert CHEMISTRY block from template
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
        
        print(f"  ✓ File written: {output_file}")
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
                # Found chemistry block start - save current chunk
                chunks.append(current_chunk)
                current_chunk = []
                in_chemistry_block = True
                chemistry_found = True
            elif in_chemistry_block and "#=========================== CONSTRAINTS ======================================" in line:
                # End of chemistry block - start new chunk with this line
                in_chemistry_block = False
                current_chunk.append(line)
            elif not in_chemistry_block:
                current_chunk.append(line)
            # Skip lines that are part of the chemistry block
        
        if current_chunk:  # Add final chunk
            chunks.append(current_chunk)
        
        # If chemistry block wasn't found, the template might already be using external chemistry
        if not chemistry_found:
            # Just split by delimiters
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
    
    def _split_template(self, template_content: List[str]) -> List[List[str]]:
        """Split template file into chunks based on delimiters."""
        chunks = []
        current_chunk = []
        
        for line in template_content:
            if "$%$%$% CHUNK DELIM %^%^%^" in line:
                chunks.append(current_chunk)
                current_chunk = []
            else:
                current_chunk.append(line)
        
        if current_chunk:  # Add final chunk
            chunks.append(current_chunk)
        
        return chunks
    
    def generate_files(self, upstream_file: str = None, downstream_file: str = None) -> Tuple[str, str]:
        """Generate both spin-up and transient input files with meander and year in filenames."""
        # Use the same timestamp for both directory creation and file naming
        timestamp = self.generation_timestamp.strftime("%Y-%m-%d_%H-%M-%S")
        
        # Extract year suffix (e.g., '19' from '2019', '18' from '2018')
        year_suffix = self.year[-2:]
        
        # Generate transient file with format: pflotran-{meander}{year_suffix}_{timestamp}.in
        transient_filename = f'pflotran-{self.meander}{year_suffix}_{timestamp}.in'
        self.assemble_input_file(transient_filename, True, upstream_file, downstream_file)
        
        # Generate spin-up file with 'spin' suffix
        spinup_filename = f'pflotran-{self.meander}{year_suffix}_{timestamp}_spin.in'
        self.assemble_input_file(spinup_filename, False)
        
        # Update restart file reference in transient file
        transient_path = self.output_dir / transient_filename
        if transient_path.exists():
            with open(transient_path, 'r') as f:
                lines = f.readlines()
            
            # Find and update restart file line to reference spin file
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

            # Generation info
            f.write(f"Generated: {self.generation_timestamp.strftime('%Y-%m-%d %H:%M:%S')} (Local Time)\n")
            f.write(f"Output Directory: {self.output_dir.absolute()}\n\n")

            # Arguments section
            f.write("Arguments\n")
            f.write("-" * 50 + "\n")
            f.write(f"  year:            {self.year}\n")
            f.write(f"  meander:         {self.meander}\n")
            f.write(f"  nx:              {self.nx}\n")
            f.write(f"  upstream_h:      {self.upstream_h}\n")
            f.write(f"  downstream_h:    {self.downstream_h}\n")
            if upstream_file:
                f.write(f"  upstream_file:   {upstream_file}\n")
            if downstream_file:
                f.write(f"  downstream_file: {downstream_file}\n")
            f.write("\n")

            # DATUM calculation info
            f.write("DATUM Calculation\n")
            f.write("-" * 50 + "\n")
            f.write(f"  First DATUM (ix=0): {self.upstream_h:.6f} m\n")
            if self.nx > 1:
                f.write(f"  Last DATUM (ix={self.nx-1}): {self.downstream_h:.6f} m\n")
                second_datum = self.upstream_h + (self.downstream_h - self.upstream_h) * (1 / (self.nx - 1))
                f.write(f"  Second DATUM (ix=1): {second_datum:.6f} m\n")
            f.write(f"  Linear interpolation between upstream and downstream\n\n")

            # Created files section
            f.write("Created Files\n")
            f.write("-" * 50 + "\n")
            f.write(f"  {spinup_file}\n")
            f.write(f"  {transient_file}\n")
            f.write(f"  generation.log\n\n")

            # Boundary condition files
            f.write("Boundary Condition Files\n")
            f.write("-" * 50 + "\n")
            f.write("  river_chem.txt\n")
            f.write("  river_transport_constraint.txt\n")
            f.write("  top_chem.txt\n")
            f.write("  top_transport_constraint.txt\n")
            f.write("  trans-top-bcs/ (directory with BC files)\n\n")

            # Template files
            f.write("Template Files Used\n")
            f.write("-" * 50 + "\n")
            f.write("  TEMPLATE-constraint.txt\n")
            f.write("  TEMPLATE-chemistry.txt\n")
            f.write("  TEMPLATE-pflotran.in\n")
            f.write("  TEMPLATE-pflotran-spin.in\n\n")

            # Copied files
            if copied_files:
                f.write("Copied Files\n")
                f.write("-" * 50 + "\n")
                for file in copied_files:
                    f.write(f"  {file}\n")

        print(f"📋 Log saved: {log_file}")
    
    def copy_required_files(self, upstream_file: str = None, downstream_file: str = None) -> None:
        """Copy required files to the output directory."""
        print("📋 Copying required files to output directory...")
        
        files_to_copy = []
        
        # Always copy hanford-cd.dat if it exists
        if os.path.exists('hanford-cd.dat'):
            files_to_copy.append(('hanford-cd.dat', 'hanford-cd.dat'))
        else:
            print("  ⚠️  hanford-cd.dat not found in current directory")
        
        # Copy upstream file if specified and exists
        if upstream_file and os.path.exists(upstream_file):
            files_to_copy.append((upstream_file, upstream_file))
        elif upstream_file:
            print(f"  ⚠️  Upstream file not found: {upstream_file}")
        
        # Copy downstream file if specified and exists
        if downstream_file and os.path.exists(downstream_file):
            files_to_copy.append((downstream_file, downstream_file))
        elif downstream_file:
            print(f"  ⚠️  Downstream file not found: {downstream_file}")
        
        # Copy template files for reference
        template_files = [
            'TEMPLATE-constraint.txt',
            'TEMPLATE-chemistry.txt',
            'TEMPLATE-pflotran.in', 
            'TEMPLATE-pflotran-spin.in'
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
    
    def test_datum_generation(self) -> None:
        """Test and validate DATUM generation logic."""
        print("\n🧪 Testing DATUM generation logic:")
        print(f"   nx = {self.nx}")
        print(f"   upstream_h = {self.upstream_h}")
        print(f"   downstream_h = {self.downstream_h}")
        
        # Generate test DATUMs
        test_datums = []
        for ix in range(self.nx):
            if self.nx == 1:
                hx = self.upstream_h
            else:
                hx = self.upstream_h + (self.downstream_h - self.upstream_h) * (ix / (self.nx - 1))
            test_datums.append(hx)
        
        # Validation
        print(f"   First DATUM (ix=0): {test_datums[0]:.6f} (should = {self.upstream_h})")
        if self.nx > 1:
            print(f"   Last DATUM (ix={self.nx-1}): {test_datums[-1]:.6f} (should = {self.downstream_h})")
            print(f"   Second DATUM (ix=1): {test_datums[1]:.6f}")
        
        # Assert correctness
        assert abs(test_datums[0] - self.upstream_h) < 1e-10, f"First DATUM incorrect!"
        if self.nx > 1:
            assert abs(test_datums[-1] - self.downstream_h) < 1e-10, f"Last DATUM incorrect!"
        
        print("   ✅ DATUM generation test PASSED!")


def main():
    """Main function with command line interface."""

    # Configuration lookup tables based on year and meander
    CONFIG = {
        ('2019', 'mzt'): {
            'nx': 108,
            'upstream_h': 1.94,
            'downstream_h': 1.66,
            'upstream_file': 'hydro_us_2019_4-21_10-2-MZT.txt',
            'downstream_file': 'hydro_dn_2019_4-21_10-2-MZT.txt'
        },
        ('2018', 'mzt'): {
            'nx': 108,
            'upstream_h': 1.84,
            'downstream_h': 1.46,
            'upstream_file': 'hydro_us_2018_4-1_10-31-MZT.txt',
            'downstream_file': 'hydro_ds_2018_4-1_10-31-MZT.txt'
        },
        ('2019', 'mcp'): {
            'nx': 122,
            'upstream_h': 1.94,
            'downstream_h': 0.91,
            'upstream_file': 'mc_up_2019_3993h.txt',
            'downstream_file': 'mc_dn_2019_3993h.txt'
        },
        ('2018', 'mcp'): {
            'nx': 122,
            'upstream_h': 1.84,
            'downstream_h': 0.96,
            'upstream_file': 'mc_us_2018_5131h-NODAM.txt',
            'downstream_file': 'mc_dn_2018_5131h-NODAM.txt'
        }
    }

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

    args = parser.parse_args()

    # Validate year
    if args.year not in ['2018', '2019']:
        print(f"\nError: Invalid year '{args.year}'")
        print("Acceptable options: 2018, 2019")
        return 1

    # Validate meander
    if args.meander not in ['mcp', 'mzt']:
        print(f"\nError: Invalid meander '{args.meander}'")
        print("Acceptable options: mcp, mzt")
        return 1

    # Get configuration for this year/meander combination
    config_key = (args.year, args.meander)
    config = CONFIG[config_key]

    # Set derived values
    args.nx = config['nx']
    args.upstream_h = config['upstream_h']
    args.downstream_h = config['downstream_h']
    args.upstream_file = config['upstream_file']
    args.downstream_file = config['downstream_file']

    print(f"\nConfiguration for {args.meander.upper()} {args.year}:")
    print(f"  nx:              {args.nx}")
    print(f"  upstream_h:      {args.upstream_h}")
    print(f"  downstream_h:    {args.downstream_h}")
    print(f"  upstream_file:   {args.upstream_file}")
    print(f"  downstream_file: {args.downstream_file}")

    try:
        # Initialize generator
        generator = PFLOTRANGenerator(
            year=args.year,
            meander=args.meander,
            nx=args.nx,
            upstream_h=args.upstream_h,
            downstream_h=args.downstream_h
        )

        # Test DATUM generation if requested
        if args.test_datum:
            generator.test_datum_generation()
            print(f"\n✅ DATUM test completed successfully!")
            return 0
        
        # Test DATUM generation before proceeding
        generator.test_datum_generation()
        
        # Generate files
        spinup_file, transient_file = generator.generate_files(
            args.upstream_file, 
            args.downstream_file
        )
        
        # Copy required files to output directory
        copied_files = generator.copy_required_files(
            args.upstream_file,
            args.downstream_file
        ) or []

        # Create combined generation log
        generator.create_run_log(
            spinup_file, transient_file,
            args.upstream_file, args.downstream_file,
            copied_files
        )

        print(f"\n✅ SUCCESS! Generated files in nested directory structure:")
        print(f"   📁 Directory: {generator.output_dir.absolute()}")
        print(f"   🔧 Spin-up: {spinup_file}")
        print(f"   ⚡ Transient: {transient_file}")
        print(f"   📋 Log: generation.log")
        if copied_files:
            print(f"   📄 Copied files: {', '.join(copied_files)}")
        print(f"\n🎯 Key Improvements in v2.2:")
        print(f"   ✅ Added --meander argument (mcp/mzt)")
        print(f"   ✅ Updated file naming: pflotran-{args.meander}{args.year[-2:]}_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.in")
        print(f"   ✅ Separate CHEMISTRY template file")
        print(f"   ✅ Fixed DATUM calculation errors")
        print(f"   ✅ Nested directory structure: ./{datetime.now().strftime('%Y-%m-%d')}/{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}/")
        print(f"   ✅ DATUM validation testing")
        print(f"   ✅ Improved error handling")
        print(f"   ✅ Auto-copy required files")
        print(f"   ✅ Local timezone support")
        
        # For backward compatibility, print the full path to spin-up file
        print(f"\n📄 Full path to spin-up file:")
        print(str(generator.output_dir / spinup_file))
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == '__main__':
    exit(main())