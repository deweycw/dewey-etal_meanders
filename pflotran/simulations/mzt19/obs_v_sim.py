from matplotlib.lines import lineStyles 
import numpy as np
import matplotlib.pyplot as plt
import sys

import pandas as pd
from pflotranutils.h5_output.calc.cross_section import CrossSection 

def plot_component(results, times, distances, startdate, ax, meander, component_name, 
                   chem_obs=None, unit=None, obs_component_name=None, reverse=False, discretization=0.5, 
                   plot_obs_average=False):
    """
    Plot any component from the results data with optional observations overlay.
    
    Parameters:
    -----------
    results : dict
        Dictionary containing simulation results by distance
    times : list
        Time points for the simulation
    distances : list
        Distance points to plot
    startdate : datetime
        Starting date for time series
    ax : matplotlib.axes
        Axes object to plot on
    meander : str
        Meander identifier ('MZ' or 'MC')
    component_name : str
        Name of the component to plot from results (e.g., 'Total_Ca++ [M]')
    chem_obs : DataFrame, optional
        Chemical observations data
    unit : str, optional
        Unit for y-axis display. If None, defaults to observation units.
        For pH, always treated as unitless regardless of input.
    obs_component_name : str, optional
        Name of component in observations data (if different from component_name)
        If None, will try to infer from component_name
    reverse : bool, default False
        Whether to reverse the sign of the simulation data
    plot_obs_average : bool, default False
        Whether to plot average observation values as horizontal lines for each location
    
    Returns:
    --------
    ax : matplotlib.axes
        Updated axes object
    """
    import matplotlib as mpl
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    import numpy as np
    
    # First, validate that the component exists in the results data
    if len(distances) == 0:
        print("⚠️  No distances provided!")
        return ax
        
    # Check component availability using the first distance
    first_distance = distances[0]
    if first_distance not in results:
        print(f"⚠️  Distance {first_distance} not found in results!")
        print(f"Available distances: {list(results.keys())}")
        return ax
    
    available_components = list(results[first_distance].keys())
    if component_name not in available_components:
        print(f"⚠️  Component '{component_name}' not found in results data!")
        
        # Suggest alternatives based on the requested component
        suggestion = _suggest_alternative_component(component_name, available_components)
        if suggestion:
            print(f"💡 Did you mean: '{suggestion}'?")
        else:
            print("📋 Available components:")
            for i, comp in enumerate(available_components[:10]):  # Show first 10
                print(f"   {comp}")
            if len(available_components) > 10:
                print(f"   ... and {len(available_components) - 10} more")
        
        return ax
    
    # Handle pH as special case - always unitless
    if component_name == 'pH' or (obs_component_name and obs_component_name == 'pH'):
        unit = 'pH'
    
    # Determine default unit based on observation data if unit not specified
    if unit is None:
        if obs_component_name is None:
            obs_component_name = _infer_obs_component_name(component_name)
        unit = _get_default_unit(obs_component_name)
        print(f"🔧 Using default unit '{unit}' based on observation data")
    
    # Set up color mapping and styling
    cmap = mpl.cm.get_cmap('viridis')
    cmaplist = [cmap(i) for i in np.arange(0, 1, 0.2)]
    
    # Distance-to-location mapping based on meander type
    if meander == 'MZ':
        loc_dist = {1: '1', 16: '2', 27: '3', 40: '4', 50: '5'}
    elif meander == 'MC':
        loc_dist = {0.5: '1', 16: '2', 31: '3', 46: '4', 60.0: '5'}
    else:
        print(f'{meander} is not a valid meander name. MC and MZ are only valid meander names.')
        return ax
    
    loc_colors = {'river': 'mediumblue', '1': cmaplist[0], '2': cmaplist[1], 
                  '3': cmaplist[2], '4': cmaplist[3], '5': cmaplist[4]}
    loc_symbols = {'river': 's', '1': 'o', '2': 'p', '3': 'd', '4': 'P', '5': 'X'}
    
    # Set up unit conversion factor for simulation results
    if unit == 'uM':
        factor = 1e6
    elif unit == 'mM':
        factor = 1e3
    elif unit == 'pH':
        factor = 1  # pH is unitless
    else:
        factor = 1  # Default to M or unitless
    
    # Extract and sort times (needed for both simulation and observation plotting)
    times_int = [int(t) for t in times]
    times_int.sort()
    
    # Plot simulation results for each distance
    components = [component_name]
    for component in components:
        for distance in distances:
            if distance in results and component in results[distance]:
                component_data = results[distance][component]
                
                # Extract concentration data
                y = []
                for t in range(len(times_int)):
                    ct = component_data[t]
                    if reverse:
                        y.append(ct * -1)
                    else:
                        y.append(ct)
                
                # Set up time axis
                if startdate and not plot_obs_average:
                    # Convert numpy datetime64 to pandas Timestamp for better matplotlib compatibility
                    if isinstance(startdate, np.datetime64):
                        import pandas as pd
                        startdate_pd = pd.Timestamp(startdate)
                    else:
                        startdate_pd = startdate
                    
                    times_delta = [np.timedelta64(int(t), 'h') for t in times_int]
                    timesx = [(startdate_pd + pd.Timedelta(hours=int(t))) for t in times_int]
                else:
                    # Use years for x-axis when plot_obs_average=True or no startdate
                    timesx = times_int
                
                # Plot the simulation data
                if distance in loc_dist:
                    ax.plot(timesx, [yp * factor for yp in y], 
                           color=loc_colors[loc_dist[distance]], 
                           linewidth=1.5, alpha=0.8)
    
    # Plot observations if available
    try:
        if chem_obs is not None:
            # Set up observation component name mapping
            if obs_component_name is None:
                obs_component_name = _infer_obs_component_name(component_name)
            
            print(f"🔍 Looking for observation component: '{obs_component_name}' (mapped from '{component_name}')")
            
            # Check if the observation component exists in the data
            if len(chem_obs.columns) > 0:
                print(f"📊 Available observation columns: {list(chem_obs.columns)}")
                if obs_component_name not in chem_obs.columns:
                    print(f"⚠️  Observation component '{obs_component_name}' not found in observation data!")
                    print(f"💡 Try specifying obs_component_name manually, e.g., obs_component_name='Ca'")
                    return ax
            
            # Set up observation locations based on meander type
            if meander == 'MZ':
                obs_locs = ['MZT1-1D', 'MZT1-2D', 'MZT1-3D', 'MZT1-4D', 'MZT1-5D']
                loc_name = {'MZT1-1D': '1', 'MZT1-2D': '2', 'MZT1-3D': '3', 
                           'MZT1-4D': '4', 'MZT1-5D': '5'}
            elif meander == 'MC':
                obs_locs = ['MCP1-1D', 'MCP1-2D', 'MCP1-3D', 'MCP1-4D', 'MCP1-5D']
                loc_name = {'MCP1-1D': '1', 'MCP1-2D': '2', 'MCP1-3D': '3', 
                           'MCP1-4D': '4', 'MCP1-5D': '5'}
            
            if plot_obs_average:
                # Plot average observation values as horizontal lines
                print(f"📈 Plotting observation averages for component '{obs_component_name}'")
                _plot_observation_averages(ax, chem_obs, obs_locs, loc_name, obs_component_name,
                                         factor, loc_colors, times_int, unit)
            else:
                # Plot individual observation points
                obs_factor = _get_obs_unit_factor(obs_component_name, unit)
                for l in obs_locs:
                    df = chem_obs[chem_obs['Well'] == l]
                    if obs_component_name in df.columns:
                        mask = df[obs_component_name].isna()
                        df = df[~mask]
                        if len(df) > 0:
                            ax.plot(df['Date'], df[obs_component_name] * obs_factor, 
                                   linestyle='-.', linewidth=0.5, 
                                   color=loc_colors[loc_name[l]], 
                                   marker=loc_symbols[loc_name[l]], 
                                   markersize=4, alpha=0.7)
    except Exception as e:
        print(f'❌ Error plotting observations: {e}')
        import traceback
        traceback.print_exc()
    
    # Format axes
    if startdate and not plot_obs_average:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%-d-%b"))
        ax.set_xlabel('Date')
    else:
        ax.set_xlabel('Years after time = 0')
        # Set x-axis limits to show full range
        if len(times_int) > 0:
            ax.set_xlim(min(times_int), max(times_int))
    
    # Set y-label based on component and unit
    ylabel = _get_ylabel(component_name, unit)
    ax.set_ylabel(ylabel)
    
    return ax


def _suggest_alternative_component(requested_component, available_components):
    """
    Suggest alternative components based on the requested component name.
    
    Parameters:
    -----------
    requested_component : str
        The component that was requested but not found
    available_components : list
        List of available components in the data
    
    Returns:
    --------
    str or None
        Suggested alternative component name or None if no good match found
    """
    
    # Create mapping of common variations
    component_patterns = {
        'Total_Ca++ [M]': ['Free_Ca++ [M]', 'CaCO3(aq) [M]', 'CaSO4(aq) [M]', 'CaCl+ [M]'],
        'Total_Mg++ [M]': ['Free_Mg++ [M]', 'MgCO3(aq) [M]', 'MgSO4(aq) [M]', 'MgCl+ [M]'],
        'Total_Na+ [M]': ['Free_Na+ [M]', 'NaCl(aq) [M]', 'NaCO3- [M]', 'NaHCO3(aq) [M]'],
        'Total_K+ [M]': ['Free_K+ [M]', 'KCl(aq) [M]', 'KSO4- [M]', 'KOH(aq) [M]'],
        'Total_SO4-- [M]': ['Free_SO4-- [M]', 'CaSO4(aq) [M]', 'MgSO4(aq) [M]', 'FeSO4(aq) [M]'],
        'Total_Cl- [M]': ['Free_Cl- [M]', 'CaCl+ [M]', 'CaCl2(aq) [M]', 'NaCl(aq) [M]'],
        'Total_HCO3- [M]': ['Free_HCO3- [M]', 'CaHCO3+ [M]', 'MgHCO3+ [M]', 'NaHCO3(aq) [M]'],
        'Total_NO3- [M]': ['Free_NO3- [M]', 'CaNO3+ [M]', 'NaNO3(aq) [M]', 'HNO3(aq) [M]'],
        'Total_Al+++ [M]': ['Free_Al+++ [M]', 'AlOH++ [M]', 'Al(OH)2+ [M]', 'AlSO4+ [M]'],
        'Total_Fe++ [M]': ['Free_Fe++ [M]', 'FeCO3(aq) [M]', 'FeSO4(aq) [M]', 'FeCl+ [M]'],
        'Total_Fe+++ [M]': ['Free_Fe+++ [M]', 'FeOH++ [M]', 'Fe(OH)2+ [M]', 'FeCl++ [M]'],
        'Total_SiO2(aq) [M]': ['Free_SiO2(aq) [M]', 'H3SiO4- [M]', 'H2SiO4-- [M]', 'NaHSiO3(aq) [M]']
    }
    
    # Check for exact pattern matches first
    if requested_component in component_patterns:
        for suggestion in component_patterns[requested_component]:
            if suggestion in available_components:
                return suggestion
    
    # If no exact pattern match, try fuzzy matching
    import re
    
    # Extract the main element/ion from the requested component
    # For "Total_Ca++ [M]", extract "Ca"
    element_match = re.search(r'(?:Total_|Free_)?([A-Za-z]+)(?:\+|\-|[0-9])*', requested_component)
    if element_match:
        element = element_match.group(1)
        
        # Look for any component containing this element
        for comp in available_components:
            if element in comp and comp != requested_component:
                return comp
    
    # Check for common substitutions
    substitutions = {
        'Total_': 'Free_',
        'Free_': 'Total_',
        '[M]': '(aq) [M]',
        '(aq) [M]': '[M]'
    }
    
    for old_pattern, new_pattern in substitutions.items():
        if old_pattern in requested_component:
            suggested = requested_component.replace(old_pattern, new_pattern)
            if suggested in available_components:
                return suggested
    
    return None


def _get_default_unit(obs_component_name):
    """
    Get the default unit based on the observation component's native units.
    
    Parameters:
    -----------
    obs_component_name : str
        Name of the observation component
    
    Returns:
    --------
    str
        Default unit for the component
    """
    # Components that are already in mM in the observation data
    obs_mM_components = ['TC', 'NPOC', 'TIC', 'NH4', 'Cl', 'NO2', 'SO4', 'NO3']
    
    # Components that are in M in the observation data  
    obs_M_components = ['Na', 'Na_sd', 'Mg', 'Mg_sd', 'Si', 'Si_sd', 'Si-1', 'Si-1_sd', 
                       'K', 'K_sd', 'Mn', 'Mn_sd', 'Ca', 'Ca_sd', 'Fe', 'Fe_sd', 
                       'Ni', 'Ni_sd', 'Cu', 'Cu_sd', 'Zn', 'Zn_sd', 'Sr', 'Sr_sd', 
                       'Ba', 'Ba_sd', 'U', 'U_sd', 'PO', 'PO_sd']
    
    # Special cases
    if obs_component_name == 'pH':
        return 'pH'
    elif obs_component_name == 'DO':
        return 'uM'  # Show DO in μM (converted from mg/L)
    elif obs_component_name in obs_mM_components:
        return 'mM'
    elif obs_component_name in obs_M_components:
        return 'M'
    else:
        # Default fallback
        return 'mM'


def _get_obs_unit_factor(obs_component_name, target_unit):
    """
    Get the conversion factor for observation data based on its native units.
    
    Parameters:
    -----------
    obs_component_name : str
        Name of the observation component
    target_unit : str
        Target unit for display (e.g., 'mM', 'uM', 'M')
    
    Returns:
    --------
    float
        Conversion factor to apply to observation data
    """
    # Components that are already in mM in the observation data
    obs_mM_components = ['TC', 'NPOC', 'TIC', 'NH4', 'Cl', 'NO2', 'SO4', 'NO3']
    
    # Components that are in M in the observation data  
    obs_M_components = ['Na', 'Na_sd', 'Mg', 'Mg_sd', 'Si', 'Si_sd', 'Si-1', 'Si-1_sd', 
                       'K', 'K_sd', 'Mn', 'Mn_sd', 'Ca', 'Ca_sd', 'Fe', 'Fe_sd', 
                       'Ni', 'Ni_sd', 'Cu', 'Cu_sd', 'Zn', 'Zn_sd', 'Sr', 'Sr_sd', 
                       'Ba', 'Ba_sd', 'U', 'U_sd', 'PO', 'PO_sd']
    
    # Components that are in mg/L in the observation data
    obs_mgL_components = ['DO']  # Dissolved Oxygen
    
    if obs_component_name in obs_mM_components:
        obs_native_unit = 'mM'
    elif obs_component_name in obs_M_components:
        obs_native_unit = 'M'
    elif obs_component_name in obs_mgL_components:
        obs_native_unit = 'mg/L'
    else:
        # Default assumption: observation data is in M
        obs_native_unit = 'M'
    
    # Handle mg/L conversions for dissolved oxygen (O2)
    if obs_native_unit == 'mg/L' and obs_component_name == 'DO':
        # Convert mg/L O2 to molar units
        # Molecular weight of O2 = 32.0 g/mol
        MW_O2 = 32.0  # g/mol
        
        if target_unit == 'M':
            factor = 1.0 / (MW_O2 * 1000)  # mg/L to M
            print(f"🔧 DO conversion: mg/L to M, factor = {factor}")
            return factor
        elif target_unit == 'mM':
            factor = 1.0 / MW_O2  # mg/L to mM
            print(f"🔧 DO conversion: mg/L to mM, factor = {factor}")
            return factor
        elif target_unit == 'uM':
            factor = 1000.0 / MW_O2  # mg/L to uM
            print(f"🔧 DO conversion: mg/L to uM, factor = {factor}")
            return factor
        else:
            return 1  # Unknown target unit, no conversion
    
    # Handle pH - always unitless, no conversion
    if obs_component_name == 'pH' or target_unit == 'pH':
        return 1
    
    # Standard conversions for other components
    if obs_native_unit == 'M' and target_unit == 'mM':
        return 1e3  # M to mM
    elif obs_native_unit == 'M' and target_unit == 'uM':
        return 1e6  # M to uM
    elif obs_native_unit == 'mM' and target_unit == 'M':
        return 1e-3  # mM to M
    elif obs_native_unit == 'mM' and target_unit == 'uM':
        return 1e3  # mM to uM
    elif obs_native_unit == 'uM' and target_unit == 'M':
        return 1e-6  # uM to M
    elif obs_native_unit == 'uM' and target_unit == 'mM':
        return 1e-3  # uM to mM
    else:
        # Same units or unknown - no conversion
        return 1


def _plot_observation_averages(ax, chem_obs, obs_locs, loc_name, obs_component_name,
                         factor, loc_colors, times_int, unit):
    """
    Plot average observation values as horizontal lines for each location.
    """
    
    # Calculate time range for horizontal lines (in years)
    time_start = min(times_int)
    time_end = max(times_int)
    
    print(f"🎯 Plotting averages for {len(obs_locs)} locations with component '{obs_component_name}'")
    
    # Get the correct conversion factor for observation data
    obs_factor = _get_obs_unit_factor(obs_component_name, unit)
    print(f"🔄 Observation unit conversion factor: {obs_factor} (to convert to {unit})")
    
    # Plot average lines for each location
    lines_plotted = 0
    for l in obs_locs:
        df = chem_obs[chem_obs['Well'] == l]
        print(f"   Location {l}: {len(df)} total observations")
        
        if obs_component_name in df.columns:
            mask = df[obs_component_name].isna()
            df = df[~mask]
            print(f"   Location {l}: {len(df)} valid observations for {obs_component_name}")
            
            if len(df) > 0:
                # Calculate average with correct unit conversion
                avg_value = df[obs_component_name].mean() * obs_factor
                print(f"   Location {l}: Raw obs average = {df[obs_component_name].mean():.3f}")
                print(f"   Location {l}: Converted average = {avg_value:.3f} {unit}")
                
                # Debug: For DO, show the conversion details
                if obs_component_name == 'DO':
                    print(f"   DO conversion factor used: {obs_factor}")
                    print(f"   Sample raw DO values: {df[obs_component_name].head(3).tolist()}")
                    print(f"   Sample converted DO values: {(df[obs_component_name].head(3) * obs_factor).tolist()}")
                
                # Plot horizontal line across the simulation time range
                ax.axhline(y=avg_value, color=loc_colors[loc_name[l]], 
                          linestyle='--', linewidth=2, alpha=0.8,
                          label=f'Avg {loc_name[l]}: {avg_value:.2f}')
                
                # Add text annotation
                x_pos = time_start + (time_end - time_start) * 0.02
                
                ax.text(x_pos, avg_value * 1.05, f'{avg_value:.2f}', 
                       color=loc_colors[loc_name[l]], fontsize=8, 
                       verticalalignment='bottom', alpha=0.9)
                
                lines_plotted += 1
            else:
                print(f"   Location {l}: No valid data for {obs_component_name}")
        else:
            print(f"   Location {l}: Column {obs_component_name} not found")
    
    print(f"✅ Successfully plotted {lines_plotted} observation average lines")


def _infer_obs_component_name(component_name):
    """
    Infer the observation component name from the simulation component name.
    
    This function maps simulation component names to observation component names.
    """
    component_mapping = {
        # Total concentrations - main ions
        'Total_Ca++ [M]': 'Ca',
        'Total_Mg++ [M]': 'Mg',
        'Total_Na+ [M]': 'Na',
        'Total_K+ [M]': 'K',
        'Total_SO4-- [M]': 'SO4',
        'Total_Cl- [M]': 'Cl',
        'Total_HCO3- [M]': 'TIC',  # Total bicarbonate maps to TIC (Total Inorganic Carbon)
        'Total_NO3- [M]': 'NO3',
        'Total_Al+++ [M]': 'Al',
        'Total_Fe++ [M]': 'Fe2',
        'Total_Fe+++ [M]': 'Fe3',
        'Total_SiO2(aq) [M]': 'Si',
        'Total_H+ [M]': 'H',
        'Total_HS- [M]': 'S',
        'Total_Ac- [M]': 'Acetate',
        'Total_O2(aq) [M]': 'DO',
        'Total_N2(aq) [M]': 'N2',
        'Total_SOC(aq) [M]': 'NPOC',  # Total SOC maps to NPOC (Non-Purgeable Organic Carbon)
        'Total_Tracer [M]': 'Tracer',
        
        # Free concentrations
        'Free_Ca++ [M]': 'Ca',  # Map free Ca to the same obs data as total Ca
        'Free_Mg++ [M]': 'Mg',  # Map free Mg to the same obs data as total Mg
        'Free_Na+ [M]': 'Na',
        'Free_K+ [M]': 'K',
        'Free_SO4-- [M]': 'SO4',
        'Free_Cl- [M]': 'Cl',
        'Free_HCO3- [M]': 'TIC',  # Free bicarbonate also maps to TIC
        'Free_NO3- [M]': 'NO3',
        'Free_Al+++ [M]': 'Al',
        'Free_Fe++ [M]': 'Fe2',
        'Free_Fe+++ [M]': 'Fe3',
        'Free_SiO2(aq) [M]': 'Si',
        'Free_H+ [M]': 'H',
        'Free_HS- [M]': 'S',
        'Free_O2(aq) [M]': 'DO',
        'Free_N2(aq) [M]': 'N2',
        'Free_SOC(aq) [M]': 'SOC',
        'Free_Tracer [M]': 'Tracer',
        
        # Dissolved gases
        'CO2(aq) [M]': 'CO2',
        'CH4(aq) [M]': 'CH4',
        'H2(aq) [M]': 'H2',
        'H2S(aq) [M]': 'H2S',
        'NH3(aq) [M]': 'NH3',
        'CO(aq) [M]': 'CO',
        'SO2(aq) [M]': 'SO2',
        
        # pH and other parameters
        'pH': 'pH',
        'Liquid_Saturation': 'Saturation',
        'Liquid_Pressure [Pa]': 'Pressure',
        'Material_ID': 'Material',
        
        # Mineral saturation indices
        'Calcite_SI': 'Calcite_SI',
        'Dolomite_SI': 'Dolomite_SI',
        'Albite_SI': 'Albite_SI',
        'Pyrite_SI': 'Pyrite_SI',
        'Ferrihydrite_SI': 'Ferrihydrite_SI',
        'Goethite_SI': 'Goethite_SI',
        
        # Mineral volume fractions
        'Calcite_VF [m^3 mnrl_m^3 bulk]': 'Calcite_VF',
        'Dolomite_VF [m^3 mnrl_m^3 bulk]': 'Dolomite_VF',
        'Albite_VF [m^3 mnrl_m^3 bulk]': 'Albite_VF',
        'Pyrite_VF [m^3 mnrl_m^3 bulk]': 'Pyrite_VF',
        'Ferrihydrite_VF [m^3 mnrl_m^3 bulk]': 'Ferrihydrite_VF',
        'Goethite_VF [m^3 mnrl_m^3 bulk]': 'Goethite_VF',
        'SOC_VF [m^3 mnrl_m^3 bulk]': 'SOC_VF',
        'SOM_VF [m^3 mnrl_m^3 bulk]': 'SOM_VF',
        
        # Velocities
        'Liquid X-Velocity [m_per_y]': 'Vel_X',
        'Liquid Y-Velocity [m_per_y]': 'Vel_Y',
        'Liquid Z-Velocity [m_per_y]': 'Vel_Z',
        'Gas X-Velocity': 'Gas_Vel_X',
        'Gas Y-Velocity': 'Gas_Vel_Y',
        'Gas Z-Velocity': 'Gas_Vel_Z',
        
        # Immobile concentrations
        'Fim [mol_m^3]': 'Fim',
        'Nim [mol_m^3]': 'Nim',
        'Sim [mol_m^3]': 'Sim',
        
        # Common complex ions that might have abbreviated names in observations
        'CaCO3(aq) [M]': 'CaCO3',
        'CaSO4(aq) [M]': 'CaSO4',
        'MgCO3(aq) [M]': 'MgCO3',
        'MgSO4(aq) [M]': 'MgSO4',
        'FeCO3(aq) [M]': 'FeCO3',
        'FeSO4(aq) [M]': 'FeSO4',
        'NH4+ [M]': 'NH4',
        'OH- [M]': 'OH',
        'CO3-- [M]': 'TIC',  # Carbonate also maps to TIC
        'Urea(aq) [M]': 'Urea',
        'CaHCO3+ [M]': 'TIC',  # Calcium bicarbonate complex also maps to TIC
        'MgHCO3+ [M]': 'TIC',  # Magnesium bicarbonate complex also maps to TIC
        'NaHCO3(aq) [M]': 'TIC',  # Sodium bicarbonate also maps to TIC
    }
    
    return component_mapping.get(component_name, component_name)


def _get_ylabel(component_name, unit):
    """
    Generate appropriate y-axis label based on component name and unit.
    """
    # Special cases for non-concentration units
    if unit == 'pH':
        return 'pH'
    elif 'Velocity' in component_name:
        return f'Velocity ({unit})'
    elif 'Pressure' in component_name:
        return f'Pressure ({unit})'
    elif 'Saturation' in component_name:
        return 'Saturation'
    elif '_SI' in component_name:
        return 'Saturation Index'
    elif '_VF' in component_name:
        return 'Volume Fraction'
    elif '_Rate' in component_name:
        return f'Rate ({unit})'
    elif 'mol_m^3' in component_name:
        return f'Concentration ({unit})'
    
    # Extract element/ion name from component name for concentrations
    label_map = {
        'Ca': 'Ca', 'Mg': 'Mg', 'Na': 'Na', 'K': 'K', 'Al': 'Al',
        'Fe++': 'Fe²⁺', 'Fe+++': 'Fe³⁺', 'SO4': 'SO₄²⁻', 'Cl': 'Cl⁻', 
        'HCO3': 'HCO₃⁻', 'NO3': 'NO₃⁻', 'CO3': 'CO₃²⁻', 'OH': 'OH⁻',
        'NH4': 'NH₄⁺', 'HS': 'HS⁻', 'SiO2': 'SiO₂', 'CO2': 'CO₂',
        'CH4': 'CH₄', 'H2S': 'H₂S', 'NH3': 'NH₃', 'O2': 'O₂',
        'N2': 'N₂', 'H2': 'H₂', 'Tracer': 'Tracer', 'SOC': 'SOC',
        'Acetate': 'Acetate', 'Urea': 'Urea', 'H+': 'H⁺'
    }
    
    # Try to find matching element/compound
    for key, symbol in label_map.items():
        if key in component_name:
            return f'{symbol} ({unit})'
    
    # Extract mineral name for mineral-related components
    if any(mineral in component_name for mineral in ['Calcite', 'Dolomite', 'Albite', 'Pyrite', 'Ferrihydrite', 'Goethite']):
        mineral_name = component_name.split('_')[0]
        if '_SI' in component_name:
            return f'{mineral_name} SI'
        elif '_VF' in component_name:
            return f'{mineral_name} VF'
        elif '_Rate' in component_name:
            return f'{mineral_name} Rate ({unit})'
    
    # Generic fallback - clean up the component name
    if 'Total_' in component_name:
        clean_name = component_name.replace('Total_', '').split('[')[0].strip()
    elif 'Free_' in component_name:
        clean_name = component_name.replace('Free_', '').split('[')[0].strip() + ' (free)'
    else:
        clean_name = component_name.split('[')[0].strip()
    
    return f'{clean_name} ({unit})'

def get_histories(file_location):
    print(file_location)
    if ('mzt' in file_location) or ('1d' in file_location):
        distances = [1.0, 16, 27, 40, 50] #m 
    else:
        distances = [0.5, 16, 31, 46, 60.]
    depths = [1.7,2.0,2.1,2.4,2.5]

    depths = [1.0,1.0,1.0,1.0,1.0]
    locs = [(i,d) for i, d in zip(distances,depths)]



    if '18' in file_location:
        year = 2018
    elif '19' in file_location:
        year = 2019

    xsection = CrossSection(file_location,'x')
    xsection.get_cells()
    components = xsection.component_list
    #xsection.print_components() #include='Rate'
    times = xsection.times
    m_locs = {i:j for i,j in zip(range(1,6),distances)}
    results_2D = {d: {} for d in distances}

    for component in components:
        i=1
        for loc in locs:
            dset = xsection.get_history_at_m_coords(component=component,meter_coords=loc)
            c_dset = dset[:,1]
            locname = m_locs[int(i)]
            results_2D[locname][component]=c_dset
            i=i+1

    return results_2D, times

if __name__ == "__main__":

    file_location = sys.argv[1]
    plot_average = sys.argv[2]


    if sys.argv[2] == 'True':
        plot_average = True 
    elif sys.argv[2] == 'False':
        plot_average = False
    files = [  file_location]

    chem_f =  '/home/christiandewey/Code/dewey-etal-meanders/data/porewater/mz_2019_porewater.csv'
    chem_obs = pd.read_csv(chem_f, parse_dates=['Date'])
    startdate = np.datetime64('2019-04-21')
    distances = [1.0, 16, 27, 40, 50] #m 
    meander = 'MZ'

    components_to_plot = [
        'pH',
        'Free_Ca++ [M]',
        'Total_HCO3- [M]',
        'Total_Mg++ [M]',
        'Total_SOC(aq) [M]',
        'Total_O2(aq) [M]'
        
    ]

    for file in files:
        results, times = get_histories(file)
        fig, axs = plt.subplots(len(components_to_plot), 1, figsize = (5, 4*len(components_to_plot)))

        for ax, comp in zip(axs, components_to_plot):

            ax = plot_component(results, times, distances, startdate, ax, meander, 
                        comp, chem_obs=chem_obs, unit='mM', 
                        plot_obs_average=plot_average)
            
        fig.tight_layout()
        plt.savefig(file_location.replace('.h5','.pdf'))