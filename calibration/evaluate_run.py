#!/usr/bin/env python
"""
Evaluate a manual calibration run against porewater observations.

Command-line version of check_calibration_results.ipynb:
  - extracts tuned parameter values from the transient .in file
  - computes per-species KGE / NSE / RMSE with PflotranProcessor
  - appends one row to tuning_log.csv (flagged [REPEAT] if params match a prior row)
  - saves spin/transient time-series and 1:1 validation plots to the run directory
  - optionally compares metrics with and without location 5 (5D, 60 m)

Usage:
    python evaluate_run.py <run_id> --note "<what changed>"
    python evaluate_run.py manual_cal028 --note "lower root resp" --no5
    python evaluate_run.py manual_cal028 --no-log --no-plots
    python evaluate_run.py mzt18_cal000 --meander mzt --year 2018
    python evaluate_run.py mzt18nd_cal000 --meander mzt --year 2018 --scenario nodam

Expects calibration/run_<run_id>/pflotran-<meander><yy>[nd]_<run_id>{.in,.h5,_spin.h5}
('nd' for the MZT 2018 no-dam scenario). Defaults to MCP 2019.
"""

__author__ = 'Christian Dewey'

import argparse
import csv
import re
import sys
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

CALIBRATION_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CALIBRATION_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))
from src.processing.pflotran import PflotranProcessor  # noqa: E402

OBS_DIR = PROJECT_ROOT / 'data/observational/porewater'
PERPENDICULAR_AXIS = 'x'

# Monitoring wells 1D-5D per meander: well IDs, sampling distance (m along
# transect), and depth (m). 'no5' is the subset used by --no5.
MEANDER_CONFIGS = {
    'mcp': {
        'code': 'MC',
        'wells': {
            'ids':       ['1', '2', '3', '4', '5'],
            'distances': [1.5, 16, 31, 46, 60.],
            'depths':    [1.9, 1.9, 1.9, 1.9, 1.9],
        },
        'no5': {
            'ids':       ['1', '2', '3'],
            'distances': [1.5, 16, 31],
            'depths':    [1.7, 1.7, 1.7],
        },
    },
    'mzt': {
        # PflotranProcessor MZ defaults
        'code': 'MZ',
        'wells': {
            'ids':       ['1', '2', '3', '4', '5'],
            'distances': [1.0, 16, 27, 40, 50],
            'depths':    [2.0, 2.0, 2.0, 2.0, 2.0],
        },
        'no5': {
            'ids':       ['1', '2', '3', '4'],
            'distances': [1.0, 16, 27, 40],
            'depths':    [2.0, 2.0, 2.0, 2.0],
        },
    },
}

# MZT 2018 river-forcing scenarios -> run-name tag (see pflotran_generator.py)
SCENARIO_TAGS = {'dam': '', 'nodam': 'nd'}

# Transient t=0 matches the hydro BC files (2018: 4-1 to 10-31, 2019: 4-21 to 10-2).
# The spin-up start date only sets the x-axis of the spin time-series plot.
YEAR_CONFIGS = {
    '2018': {'spin_start': np.datetime64('2018-04-01'), 'trans_start': np.datetime64('2018-04-01')},
    '2019': {'spin_start': np.datetime64('2019-04-01'), 'trans_start': np.datetime64('2019-04-21')},
}

COMPONENTS = [
    'Total_HCO3- [M]',
    'Total_SO4-- [M]',
    'Total_Ca++ [M]',
    'Free_Fe++ [M]',
    'Total_NO3- [M]',
    'Total_Fe++ [M]',
    'Free_O2(aq) [M]',
    'pH',
]

# (component, title, unit) laid out on a 3x2 grid
VALIDATION_PANELS = [
    [('Total_HCO3- [M]', 'DIC (Total)', 'mM'), ('pH', 'pH', None)],
    [('Free_Fe++ [M]', 'Fe++ (Free)', 'mM'), ('Total_Ca++ [M]', 'Ca++', 'mM')],
    [('Total_K+ [M]', 'K+', 'mM'), ('Total_SO4-- [M]', 'SO4--', 'mM')],
]

# Parameter regex patterns (searched with re.DOTALL)
PARAM_PATTERNS = {
    'aero_rate':   r'SOC\(aq\).*?O2\(aq\).*?RATE_CONSTANT\s+(\S+)',
    'aero_k_o2':   r'SOC\(aq\).*?O2\(aq\).*?HALF_SATURATION_CONSTANT\s+(\S+)',
    'denit_rmax':  r'JINBETHKE_NITRATE_ACETATE\s+RMAX\s+(\S+)',
    'denit_k_acc': r'JINBETHKE_NITRATE_ACETATE.*?K_ACCEPTOR\s+(\S+)',
    'fh_rmax':     r'JINBETHKE_FERRIHYDRITE_ACETATE\s+RMAX\s+(\S+)',
    'fh_k_donor':  r'JINBETHKE_FERRIHYDRITE_ACETATE.*?K_DONOR\s+(\S+)',
    'msr_k_donor': r'JINBETHKE_SULFATE_ACETATE.*?K_DONOR\s+(\S+)',
    'root_resp':   r'Root_Respiration\s+DISSOLUTION_RATE_CONSTANT\s+(\S+)',
}


def fortran_float(s):
    return float(s.strip().lower().replace('d', 'e'))


def fmt_param(v):
    """Format a parameter value to 3 significant figures in scientific notation."""
    if isinstance(v, (int, float, np.floating)) and not np.isnan(v):
        return f"{v:.2e}"
    return v


def fmt_metric(v):
    """Format a metric value to 3 significant figures."""
    if isinstance(v, (int, float, np.floating)) and not np.isnan(v):
        return f"{v:.3g}"
    return v


def extract_params(infile):
    text = Path(infile).read_text()
    vals = {}
    for name, pattern in PARAM_PATTERNS.items():
        m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        vals[name] = fortran_float(m.group(1)) if m else np.nan
    return vals


def make_processor(h5_path, meander_code, wells):
    proc = PflotranProcessor(
        h5_path=str(h5_path),
        meander=meander_code,
        perpendicular_axis=PERPENDICULAR_AXIS,
        distances=wells['distances'],
        depths=wells['depths'],
    )
    # PflotranProcessor pairs observations with simulated values by looking up
    # each distance in config['loc_dist'] (default MC keys: 0.5, 16, 31, 46, 60).
    # Any distance not in that map (e.g. 1.5) silently drops that well's
    # observations, so map the distances actually sampled to their well IDs.
    proc.config['loc_dist'] = dict(zip(wells['distances'], wells['ids']))
    return proc


def compute_metrics(proc, startdate, chem_obs):
    """Per-component KGE, NSE, RMSE, n, plus mean KGE across components."""
    summary = proc.calculate_kge(startdate=startdate, chem_obs=chem_obs)['summary']
    metrics = {}
    for _, row in summary.iterrows():
        comp = row['Obs']  # observation column name (TIC, Fe, pH, Ca, etc.)
        metrics[f'KGE_{comp}'] = row['KGE']
        metrics[f'NSE_{comp}'] = row['NSE']
        metrics[f'RMSE_{comp}'] = row['RMSE']
        metrics[f'n_{comp}'] = row['n']
    metrics['KGE_mean'] = summary['KGE'].mean()

    # KGE divides by the observed std/mean, so constant observations (e.g. values
    # all at a detection limit) produce huge values that swamp KGE_mean.
    for _, row in summary.drop_duplicates('Obs', keep='last').iterrows():
        if not np.isfinite(row['KGE']) or abs(row['KGE']) > 1e3:
            print(f"WARNING: KGE_{row['Obs']} = {row['KGE']:.3g} -- observations may be "
                  f"constant (zero variance); KGE_mean is not meaningful")
    return metrics


def check_repeat(log_path, param_keys, formatted_params):
    """Check if formatted param values already exist in the log."""
    if not log_path.exists():
        return False
    with open(log_path, newline='') as f:
        for row in csv.DictReader(f):
            if all(row.get(k) == str(formatted_params[k]) for k in param_keys):
                return True
    return False


def append_log(log_path, run_id, meander_code, note, params, metrics):
    param_keys = list(PARAM_PATTERNS.keys())
    fields = ['timestamp', 'run', 'meander', 'note'] + param_keys + sorted(metrics.keys())
    formatted_params = {k: fmt_param(v) for k, v in params.items()}

    if check_repeat(log_path, param_keys, formatted_params):
        print("WARNING: parameters match an existing entry -- flagged as REPEAT")
        note = f"{note} [REPEAT]"

    row = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'run': run_id,
        'meander': meander_code,
        'note': note,
    }
    row.update(formatted_params)
    row.update({k: fmt_metric(v) for k, v in metrics.items()})

    write_hdr = not log_path.exists()
    with open(log_path, 'a', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        if write_hdr:
            w.writeheader()
        w.writerow(row)
    print(f"Logged -> {log_path}")


def plot_timeseries(proc, startdate, chem_obs, out_path):
    fig, axs = plt.subplots(len(COMPONENTS), 1, figsize=(6.5, 16))
    for component, ax in zip(COMPONENTS, axs):
        proc.plot_component_histories(
            component_name=component, startdate=startdate, ax=ax, chem_obs=chem_obs)
        ax.set_title(component)
    fig.tight_layout()
    fig.savefig(out_path, dpi=200, bbox_inches='tight')
    plt.close(fig)
    print(f"Saved -> {out_path}")


def plot_validation(proc, startdate, chem_obs, out_path):
    fig, axs = plt.subplots(3, 2, figsize=(8, 11))
    for i, panel_row in enumerate(VALIDATION_PANELS):
        for j, (component, title, unit) in enumerate(panel_row):
            kwargs = {'unit': unit} if unit else {}
            ax = proc.plot_validation(
                component, startdate=startdate, chem_obs=chem_obs,
                ax=axs[i, j], show_legend=False, **kwargs)
            ax.set_title(title)
    sns.despine()
    fig.tight_layout()
    fig.savefig(out_path, dpi=200, bbox_inches='tight')
    plt.close(fig)
    print(f"Saved -> {out_path}")


def print_summary(run_id, note, params, metrics):
    print(f"\n{'─'*55}")
    print(f"Run: {run_id}  {note}")
    print(f"{'─'*55}")
    print("Parameters:")
    for k, v in params.items():
        print(f"  {k:<16s} {fmt_param(v)}")
    print("\nMetrics:")
    for k, v in sorted(metrics.items()):
        print(f"  {k:<16s} {fmt_metric(v)}")
    print(f"{'─'*55}")


def print_no5_comparison(metrics, metrics_no5):
    print(f"\n{'─'*60}")
    print("Comparison: all locations vs excluding location 5 (5D)")
    print(f"{'─'*60}")
    print(f"{'Metric':<16s} {'All locs':>10s} {'No loc 5':>10s} {'Delta':>10s}")
    print(f"{'─'*60}")
    for k in sorted(metrics.keys()):
        if k not in metrics_no5:
            continue
        v_all, v_no5 = metrics[k], metrics_no5[k]
        line = f"  {k:<16s} {fmt_metric(v_all):>10s} {fmt_metric(v_no5):>10s}"
        if isinstance(v_all, (int, float, np.floating)) and isinstance(v_no5, (int, float, np.floating)):
            line += f" {v_no5 - v_all:>+10.3f}"
        print(line)
    print(f"{'─'*60}")


def main():
    parser = argparse.ArgumentParser(
        description='Evaluate a calibration run and log it to tuning_log.csv',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('run_id', help="Run ID without the 'run_' prefix, e.g. manual_cal028")
    parser.add_argument('--meander', choices=sorted(MEANDER_CONFIGS), default='mcp',
                        help='Meander transect (default: mcp)')
    parser.add_argument('--year', choices=sorted(YEAR_CONFIGS), default='2019',
                        help='Simulation year (default: 2019)')
    parser.add_argument('--scenario', choices=sorted(SCENARIO_TAGS), default=None,
                        help='MZT 2018 only: dam (default) or nodam')
    parser.add_argument('--note', default='', help='Description of what changed in this run')
    parser.add_argument('--no-log', action='store_true', help='Do not append to tuning_log.csv')
    parser.add_argument('--no-plots', action='store_true', help='Skip time-series and validation plots')
    parser.add_argument('--no5', action='store_true',
                        help='Also compute metrics and plots excluding location 5')
    parser.add_argument('--log', type=Path, default=CALIBRATION_DIR / 'tuning_log.csv',
                        help='Path to the tuning log CSV (default: calibration/tuning_log.csv)')
    parser.add_argument('--obs', type=Path, default=None,
                        help='Porewater observations CSV '
                             '(default: data/observational/porewater/<mc|mz>_<year>_porewater.csv)')
    args = parser.parse_args()

    mcfg = MEANDER_CONFIGS[args.meander]
    ycfg = YEAR_CONFIGS[args.year]
    code = mcfg['code']
    if args.scenario and (args.meander, args.year) != ('mzt', '2018'):
        print("ERROR: --scenario applies only to --meander mzt --year 2018")
        return 1
    tag = SCENARIO_TAGS.get(args.scenario, '')
    log_code = f'{code}-{args.scenario}' if args.scenario == 'nodam' else code
    obs_file = args.obs or OBS_DIR / f'{code.lower()}_{args.year}_porewater.csv'

    run_id = args.run_id.removeprefix('run_')
    run_dir = CALIBRATION_DIR / f'run_{run_id}'
    prefix = f'pflotran-{args.meander}{args.year[-2:]}{tag}_{run_id}'
    trans_in = run_dir / f'{prefix}.in'
    trans_h5 = run_dir / f'{prefix}.h5'
    spin_h5 = run_dir / f'{prefix}_spin.h5'

    for f in (trans_in, trans_h5, obs_file):
        if not f.exists():
            print(f"ERROR: required file not found: {f}")
            return 1

    label = f"{args.meander.upper()} {args.year}{' ' + args.scenario if args.scenario else ''}"
    print(f"Evaluating {label} run '{run_id}' against {obs_file.name}")
    chem_obs = pd.read_csv(obs_file, parse_dates=['Date'])

    params = extract_params(trans_in)
    trans_p = make_processor(trans_h5, code, mcfg['wells'])
    metrics = compute_metrics(trans_p, ycfg['trans_start'], chem_obs)
    print_summary(run_id, args.note, params, metrics)

    if not args.no_log:
        append_log(args.log, run_id, log_code, args.note, params, metrics)

    if not args.no_plots:
        if spin_h5.exists():
            spin_p = make_processor(spin_h5, code, mcfg['wells'])
            plot_timeseries(spin_p, ycfg['spin_start'], chem_obs, run_dir / f'{run_id}_spin_timeseries.png')
        else:
            print(f"WARNING: spin output not found, skipping spin plot: {spin_h5}")
        plot_timeseries(trans_p, ycfg['trans_start'], chem_obs, run_dir / f'{run_id}_trans_timeseries.png')
        plot_validation(trans_p, ycfg['trans_start'], chem_obs, run_dir / f'{run_id}_validation.png')

    if args.no5:
        proc_no5 = make_processor(trans_h5, code, mcfg['no5'])
        metrics_no5 = compute_metrics(proc_no5, ycfg['trans_start'], chem_obs)
        print_no5_comparison(metrics, metrics_no5)
        if not args.no_plots:
            plot_timeseries(proc_no5, ycfg['trans_start'], chem_obs,
                            run_dir / f'{run_id}_trans_timeseries_no5.png')
            plot_validation(proc_no5, ycfg['trans_start'], chem_obs, run_dir / f'{run_id}_validation_no5.png')

    return 0


if __name__ == '__main__':
    sys.exit(main())
