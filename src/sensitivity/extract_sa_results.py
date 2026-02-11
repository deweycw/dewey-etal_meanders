"""
Extract PFLOTRAN model output at observation points for Morris sensitivity analysis.

Loops over SA runs (run000–run339), extracts simulated values at 5 MCP observation
wells, matches to field measurements, and computes objective function values.

Outputs:
    extracted_results.csv — paired obs/model values at each well and date
    objective_function_values.csv — per-run objective function components
"""

import argparse
import sys
import numpy as np
import pandas as pd
from pathlib import Path

# Project root for resolving relative data paths
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent.parent

from pflotranutils.processor import PflotranProcessor

# --- Configuration ---
STARTDATE = np.datetime64('2019-04-21')
SITE = 'MC'
TARGET_COMPONENTS = [
    'Total_HCO3- [M]',
    'Total_Fe++ [M]',
    'pH',
    'Total_Ca++ [M]',
]
# Short names for output columns
COMPONENT_SHORT = {
    'Total_HCO3- [M]': 'DIC',
    'Total_Fe++ [M]': 'Fe',
    'pH': 'pH',
    'Total_Ca++ [M]': 'Ca',
}
# Observation column names (from COMPONENT_TO_OBS_MAP)
COMPONENT_OBS_COL = {
    'Total_HCO3- [M]': 'TIC',
    'Total_Fe++ [M]': 'Fe',
    'pH': 'pH',
    'Total_Ca++ [M]': 'Ca',
}
# TIC is in mM in obs data; Fe, Ca in M; pH unitless
OBS_MM_COMPONENTS = ['TIC']
# Well configuration from MEANDER_CONFIG['MC']
WELLS = ['MCP1-1D', 'MCP1-2D', 'MCP1-3D', 'MCP1-4D', 'MCP1-5D']
DISTANCES = [0.5, 16, 31, 46, 60.0]
DEPTHS = [1.7, 2.0, 2.1, 2.4, 2.5]
WELL_TO_DISTANCE = dict(zip(WELLS, DISTANCES))
WELL_TO_DEPTH = dict(zip(WELLS, DEPTHS))
DISTANCE_TO_WELL = {d: w for d, w in zip(DISTANCES, WELLS)}

DEFAULT_SENSITIVITY_DIR = '/lustre/dewey/users/4315/sensitivity'
DEFAULT_OBS_CSV = str(_PROJECT_ROOT / 'mc_2019_porewater.csv')


def load_failed_runs(sensitivity_dir: str) -> set:
    """Parse failed_runs.log and return set of 3-digit run ID strings."""
    failed = set()
    log_path = Path(sensitivity_dir) / 'failed_runs.log'
    if not log_path.exists():
        print(f"No failed_runs.log found at {log_path}")
        return failed

    with open(log_path) as f:
        for line in f:
            parts = line.strip().split()
            if not parts:
                continue
            run_id = parts[0]
            # Skip non-numeric entries like 'default'
            if not run_id.isdigit():
                continue
            # Pad to 3 digits
            failed.add(run_id.zfill(3))

    print(f"Loaded {len(failed)} failed runs from {log_path}")
    return failed


def load_observations(obs_csv: str) -> pd.DataFrame:
    """Load observation CSV, filter to MCP1-*D wells, replace sentinels with NaN."""
    df = pd.read_csv(obs_csv, parse_dates=['Date'], date_format='%m/%d/%y')

    # Filter to MCP wells
    df = df[df['Well'].isin(WELLS)].copy()

    # Replace sentinel values
    df = df.replace(-999, np.nan)
    df = df.replace(-9.99e+02, np.nan)

    print(f"Loaded {len(df)} observation rows for wells: {WELLS}")
    return df


def extract_run(run_id: str, sensitivity_dir: str):
    """
    Extract model output for a single run.

    Returns (results_dict, times_array) or (None, None) on failure.
    results_dict: {distance: {component: values_array}}
    """
    run_dir = Path(sensitivity_dir) / f'run{run_id}'
    h5_name = f'pflotran-mcp19_run{run_id}.h5'
    h5_path = run_dir / h5_name

    if not h5_path.exists():
        return None, None

    try:
        processor = PflotranProcessor(
            h5_path=str(h5_path),
            meander='MC',
            perpendicular_axis='x'
        )
        results, times = processor.get_histories(components=TARGET_COMPONENTS)
        # Close HDF5 file handle (no close method in base class)
        processor.h5_data.close()
        return results, times
    except Exception as e:
        print(f"  Error extracting run{run_id}: {e}")
        try:
            processor.h5_data.close()
        except Exception:
            pass
        return None, None


def match_obs_to_model(obs_df: pd.DataFrame, results: dict, times: np.ndarray,
                       max_time_diff_hours: float = 12.0) -> list:
    """
    Match observation data to nearest model timestep for each well and date.

    Returns list of dicts with paired obs/model values.
    """
    # Convert model times (hours) to datetimes
    sim_datetimes = np.array([STARTDATE + np.timedelta64(int(t), 'h') for t in times])

    matched = []

    for well in WELLS:
        distance = WELL_TO_DISTANCE[well]
        depth = WELL_TO_DEPTH[well]

        if distance not in results:
            continue

        well_obs = obs_df[obs_df['Well'] == well]

        for _, row in well_obs.iterrows():
            obs_date = row['Date']
            if pd.isna(obs_date):
                continue

            if hasattr(obs_date, 'to_numpy'):
                obs_dt = obs_date.to_numpy()
            else:
                obs_dt = np.datetime64(obs_date)

            # Find nearest model timestep
            time_diffs = np.abs((obs_dt - sim_datetimes).astype('timedelta64[h]').astype(float))
            closest_idx = int(np.argmin(time_diffs))

            if time_diffs[closest_idx] > max_time_diff_hours:
                continue

            record = {
                'obs_point_id': well,
                'obs_y': distance,
                'obs_z': depth,
                'obs_time': str(obs_date.date()) if hasattr(obs_date, 'date') else str(obs_date),
            }

            for comp in TARGET_COMPONENTS:
                short = COMPONENT_SHORT[comp]
                obs_col = COMPONENT_OBS_COL[comp]

                # Get observation value
                obs_val = row.get(obs_col, np.nan)
                if obs_val is not None and not pd.isna(obs_val):
                    # Unit conversion: TIC obs is in mM -> convert to M
                    if obs_col in OBS_MM_COMPONENTS:
                        obs_val = obs_val * 1e-3
                else:
                    obs_val = np.nan

                # Get model value
                if comp in results[distance]:
                    mod_val = results[distance][comp][closest_idx]
                else:
                    mod_val = np.nan

                record[f'{short}_obs'] = obs_val
                record[f'{short}_mod'] = mod_val

            matched.append(record)

    return matched


def compute_objective(matched: list) -> dict:
    """
    Compute objective function from matched obs/model pairs.

    J_DIC = sum(log10(DIC_mod) - log10(DIC_obs))^2
    J_Fe  = sum(log10(Fe_mod) - log10(Fe_obs))^2
    J_pH  = sum(pH_mod - pH_obs)^2
    J_Ca  = sum(log10(Ca_mod) - log10(Ca_obs))^2
    J_total = J_DIC + J_Fe + J_pH + J_Ca
    """
    if not matched:
        return {
            'J_DIC': np.nan, 'J_Fe': np.nan, 'J_pH': np.nan,
            'J_Ca': np.nan, 'J_total': np.nan,
        }

    log_components = ['DIC', 'Fe', 'Ca']
    linear_components = ['pH']

    objective = {}
    total = 0.0

    for short in log_components:
        obs_key = f'{short}_obs'
        mod_key = f'{short}_mod'
        ss = 0.0
        count = 0
        for rec in matched:
            o = rec[obs_key]
            m = rec[mod_key]
            if np.isfinite(o) and np.isfinite(m) and o > 0 and m > 0:
                ss += (np.log10(m) - np.log10(o)) ** 2
                count += 1
        objective[f'J_{short}'] = ss if count > 0 else np.nan
        if count > 0:
            total += ss

    for short in linear_components:
        obs_key = f'{short}_obs'
        mod_key = f'{short}_mod'
        ss = 0.0
        count = 0
        for rec in matched:
            o = rec[obs_key]
            m = rec[mod_key]
            if np.isfinite(o) and np.isfinite(m):
                ss += (m - o) ** 2
                count += 1
        objective[f'J_{short}'] = ss if count > 0 else np.nan
        if count > 0:
            total += ss

    objective['J_total'] = total if any(np.isfinite(v) for v in objective.values()) else np.nan
    return objective


def main():
    parser = argparse.ArgumentParser(
        description='Extract PFLOTRAN SA results at observation points'
    )
    parser.add_argument('--sensitivity-dir', default=DEFAULT_SENSITIVITY_DIR,
                        help='Path to sensitivity run directories')
    parser.add_argument('--obs-csv', default=None,
                        help='Path to observation CSV')
    parser.add_argument('--output-dir', default=None,
                        help='Output directory (default: same as sensitivity-dir)')
    parser.add_argument('--n-runs', type=int, default=340,
                        help='Number of runs to process')
    args = parser.parse_args()

    sensitivity_dir = args.sensitivity_dir
    obs_csv = args.obs_csv or DEFAULT_OBS_CSV
    output_dir = args.output_dir or sensitivity_dir
    n_runs = args.n_runs

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Load failed runs and observations
    failed_runs = load_failed_runs(sensitivity_dir)
    obs_df = load_observations(obs_csv)

    all_matched = []
    obj_rows = []

    for i in range(n_runs):
        run_id = f'{i:03d}'

        if i % 10 == 0:
            print(f"Processing run {run_id} ({i}/{n_runs})...")

        # Check if failed
        if run_id in failed_runs:
            obj_rows.append({
                'run_id': run_id,
                'J_DIC': np.nan, 'J_Fe': np.nan, 'J_pH': np.nan,
                'J_Ca': np.nan, 'J_total': np.nan,
                'status': 'failed',
            })
            continue

        # Extract model output
        results, times = extract_run(run_id, sensitivity_dir)

        if results is None:
            obj_rows.append({
                'run_id': run_id,
                'J_DIC': np.nan, 'J_Fe': np.nan, 'J_pH': np.nan,
                'J_Ca': np.nan, 'J_total': np.nan,
                'status': 'missing',
            })
            continue

        # Match observations to model
        matched = match_obs_to_model(obs_df, results, times)

        # Add run_id to matched records
        for rec in matched:
            rec['run_id'] = run_id
        all_matched.extend(matched)

        # Compute objective function
        obj = compute_objective(matched)
        obj['run_id'] = run_id
        obj['status'] = 'success'
        obj_rows.append(obj)

    # Write extracted results CSV
    results_path = Path(output_dir) / 'extracted_results.csv'
    if all_matched:
        results_df = pd.DataFrame(all_matched)
        col_order = ['run_id', 'obs_point_id', 'obs_y', 'obs_z', 'obs_time',
                     'DIC_obs', 'Fe_obs', 'pH_obs', 'Ca_obs',
                     'DIC_mod', 'Fe_mod', 'pH_mod', 'Ca_mod']
        results_df = results_df[col_order]
        results_df.to_csv(results_path, index=False)
        print(f"\nWrote {len(results_df)} matched records to {results_path}")
    else:
        print("\nNo matched records found.")

    # Write objective function CSV
    obj_path = Path(output_dir) / 'objective_function_values.csv'
    obj_df = pd.DataFrame(obj_rows)
    col_order = ['run_id', 'J_DIC', 'J_Fe', 'J_pH', 'J_Ca', 'J_total', 'status']
    obj_df = obj_df[col_order]
    obj_df.to_csv(obj_path, index=False)
    print(f"Wrote {len(obj_df)} objective function rows to {obj_path}")


if __name__ == '__main__':
    main()
