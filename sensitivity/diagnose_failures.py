"""
Diagnose Morris sensitivity analysis failures.
Maps failed run IDs back to parameter values in the sampling matrix
and identifies which parameters and extremes are associated with failures.
"""

import numpy as np
import pandas as pd
from pathlib import Path

# ============================================================
# Configuration
# ============================================================
SENSITIVITY_PATH = Path.home() / "Code" / "dewey-etal_meanders" / "sensitivity"
FAILED_RUNS_LOG = SENSITIVITY_PATH / "failed_runs.log"
MORRIS_SAMPLES_CSV = SENSITIVITY_PATH / "morris_parameter_sets.csv"

# Parameter names (must match SALib problem definition)
PARAM_NAMES = [
    'calcite_rate', 'fh_rmax', 'fh_k_donor', 'fh_SA',
    'gt_rmax', 'gt_k_donor', 'gt_SA', 'root_resp',
    'msr_rmax', 'msr_k_donor', 'msr_k_acceptor',
    'denit_rmax', 'denit_k_donor', 'denit_k_acceptor',
    'aero_rate', 'aero_k_o2',
]

# Parameter bounds (real space)
BOUNDS = {
    'calcite_rate':     (1.55e-07, 1.55e-05),
    'fh_rmax':          (2.50e-07, 2.50e-05),
    'fh_k_donor':       (1.00e-07, 1.00e-05),
    'fh_SA':            (1.08e+06, 1.08e+08),
    'gt_rmax':          (2.50e-08, 2.50e-06),
    'gt_k_donor':       (1.00e-07, 1.00e-05),
    'gt_SA':            (2.83e+05, 2.83e+07),
    'root_resp':        (7.94e-14, 7.94e-12),
    'msr_rmax':         (2.50e-08, 2.50e-06),
    'msr_k_donor':      (5.00e-07, 5.00e-05),
    'msr_k_acceptor':   (1.00e-05, 1.00e-03),
    'denit_rmax':       (1.00e-07, 1.00e-05),
    'denit_k_donor':    (1.00e-06, 1.00e-04),
    'denit_k_acceptor': (1.00e-06, 1.00e-04),
    'aero_rate':        (1.00e-10, 1.00e-08),
    'aero_k_o2':        (1.00e-05, 1.00e-03),
}

# ============================================================
# Load data
# ============================================================

# Load Morris sampling matrix
samples = pd.read_csv(MORRIS_SAMPLES_CSV, index_col='run_id')

# Parse failed runs log
# Expected format per line: "RUN_ID STAGE"
# e.g., "045 SPIN_FAIL"
failed_runs = []
with open(FAILED_RUNS_LOG) as f:
    for line in f:
        parts = line.strip().split()
        if len(parts) >= 2:
            failed_runs.append({
                'run_id': int(parts[0]),
                'stage': parts[1],
            })

failed_df = pd.DataFrame(failed_runs)
failed_ids = set(failed_df['run_id'])

n_total = len(samples)
n_failed = len(failed_ids)
print(f"Total runs: {n_total}")
print(f"Failed runs: {n_failed} ({100 * n_failed / n_total:.1f}%)")

# ============================================================
# 1. Failure by stage (spin-up vs main)
# ============================================================
print("\n" + "=" * 60)
print("FAILURES BY STAGE")
print("=" * 60)
print(failed_df['stage'].value_counts().to_string())

# ============================================================
# 2. Failure by trajectory
# ============================================================
n_params = 16
n_per_trajectory = n_params + 1

failed_df['trajectory'] = failed_df['run_id'] // n_per_trajectory

print("\n" + "=" * 60)
print("FAILURES BY TRAJECTORY")
print("=" * 60)
traj_counts = failed_df['trajectory'].value_counts().sort_index()
print(f"Trajectories with failures: {len(traj_counts)} / 20")
print(f"\nFailures per trajectory:")
print(traj_counts.to_string())

# ============================================================
# 3. Normalized parameter positions for failed runs
# ============================================================

def normalize_log(value, lo, hi):
    """Normalize a value to [0, 1] in log10 space."""
    return (np.log10(value) - np.log10(lo)) / (np.log10(hi) - np.log10(lo))

norm_positions = pd.DataFrame(index=samples.index, columns=PARAM_NAMES, dtype=float)
for param in PARAM_NAMES:
    lo, hi = BOUNDS[param]
    norm_positions[param] = samples[param].apply(lambda v: normalize_log(v, lo, hi))

failed_norm = norm_positions.loc[norm_positions.index.isin(failed_ids)]
success_norm = norm_positions.loc[~norm_positions.index.isin(failed_ids)]

# ============================================================
# 4. Compare parameter distributions: failed vs successful
# ============================================================
print("\n" + "=" * 60)
print("PARAMETER POSITIONS: FAILED vs SUCCESSFUL RUNS")
print("(Normalized 0-1 in log space; 0 = min bound, 1 = max bound)")
print("=" * 60)

print(f"\n{'Parameter':<22} {'Failed mean':>12} {'Success mean':>13} {'Difference':>11}")
print("-" * 60)
for param in PARAM_NAMES:
    f_mean = failed_norm[param].mean()
    s_mean = success_norm[param].mean()
    diff = f_mean - s_mean
    flag = " ***" if abs(diff) > 0.15 else ""
    print(f"{param:<22} {f_mean:>12.3f} {s_mean:>13.3f} {diff:>+11.3f}{flag}")

print("\n*** = difference > 0.15, suggesting this parameter's extremes")
print("      are associated with failure")

# ============================================================
# 5. Failure rate at parameter extremes
# ============================================================
print("\n" + "=" * 60)
print("FAILURE RATE AT PARAMETER EXTREMES")
print("(Runs in bottom 25% or top 25% of each parameter's range)")
print("=" * 60)

# Thresholds for flagging problematic parameters
FAIL_RATE_THRESHOLD = 25.0  # % failure rate at extreme to flag
MEAN_DIFF_THRESHOLD = 0.15  # normalized position difference to flag

# Collect diagnostic data for summary
param_diagnostics = {}

print(f"\n{'Parameter':<22} {'Fail% (low 25%)':>16} {'Fail% (mid 50%)':>16} {'Fail% (high 25%)':>17}")
print("-" * 73)
for param in PARAM_NAMES:
    low_mask = norm_positions[param] <= 0.25
    mid_mask = (norm_positions[param] > 0.25) & (norm_positions[param] < 0.75)
    high_mask = norm_positions[param] >= 0.75

    low_fail = norm_positions.index[low_mask].isin(failed_ids).mean() * 100
    mid_fail = norm_positions.index[mid_mask].isin(failed_ids).mean() * 100
    high_fail = norm_positions.index[high_mask].isin(failed_ids).mean() * 100

    # Calculate mean difference
    f_mean = failed_norm[param].mean()
    s_mean = success_norm[param].mean()
    mean_diff = f_mean - s_mean

    # Store diagnostics
    param_diagnostics[param] = {
        'low_fail': low_fail,
        'mid_fail': mid_fail,
        'high_fail': high_fail,
        'mean_diff': mean_diff,
        'current_bounds': BOUNDS[param],
    }

    flag = " ***" if (low_fail > FAIL_RATE_THRESHOLD or high_fail > FAIL_RATE_THRESHOLD) else ""
    print(f"{param:<22} {low_fail:>15.1f}% {mid_fail:>15.1f}% {high_fail:>16.1f}%{flag}")

print("\n*** = failure rate > 25% at one extreme")

# ============================================================
# 6. Parameter values for all failed runs
# ============================================================
print("\n" + "=" * 60)
print("PARAMETER VALUES FOR FAILED RUNS (log10)")
print("=" * 60)
failed_samples = samples.loc[samples.index.isin(failed_ids)].copy()
for param in PARAM_NAMES:
    failed_samples[param] = np.log10(failed_samples[param])
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 200)
print(failed_samples.to_string())

# ============================================================
# 7. RECOMMENDATIONS: Parameters that need range updates
# ============================================================
print("\n")
print("=" * 73)
print("  RECOMMENDED PARAMETER RANGE UPDATES")
print("=" * 73)

# Identify parameters needing updates
needs_update = []

for param, diag in param_diagnostics.items():
    issues = []
    recommendation = None
    lo, hi = diag['current_bounds']

    # Check for high failure rate at low extreme
    if diag['low_fail'] > FAIL_RATE_THRESHOLD:
        issues.append(f"high failure rate ({diag['low_fail']:.1f}%) at LOW values")
        recommendation = "RAISE lower bound"

    # Check for high failure rate at high extreme
    if diag['high_fail'] > FAIL_RATE_THRESHOLD:
        issues.append(f"high failure rate ({diag['high_fail']:.1f}%) at HIGH values")
        recommendation = "LOWER upper bound"

    # Check mean difference (secondary indicator)
    if abs(diag['mean_diff']) > MEAN_DIFF_THRESHOLD:
        if diag['mean_diff'] < 0 and not any("LOW" in i for i in issues):
            issues.append(f"failed runs skew LOW (diff={diag['mean_diff']:+.3f})")
            if recommendation is None:
                recommendation = "Consider RAISING lower bound"
        elif diag['mean_diff'] > 0 and not any("HIGH" in i for i in issues):
            issues.append(f"failed runs skew HIGH (diff={diag['mean_diff']:+.3f})")
            if recommendation is None:
                recommendation = "Consider LOWERING upper bound"

    # If both extremes have high failure, note that
    if diag['low_fail'] > FAIL_RATE_THRESHOLD and diag['high_fail'] > FAIL_RATE_THRESHOLD:
        recommendation = "NARROW range (raise lower AND lower upper)"

    if issues:
        needs_update.append({
            'param': param,
            'issues': issues,
            'recommendation': recommendation,
            'current_lo': lo,
            'current_hi': hi,
        })

if not needs_update:
    print("\nNo parameters identified as needing range updates.")
    print("All parameters have acceptable failure rates across their ranges.")
else:
    print(f"\n{len(needs_update)} parameter(s) identified for potential range adjustment:\n")

    for i, item in enumerate(needs_update, 1):
        print(f"{i}. {item['param']}")
        print(f"   Current bounds: [{item['current_lo']:.2e}, {item['current_hi']:.2e}]")
        for issue in item['issues']:
            print(f"   - {issue}")
        print(f"   >>> RECOMMENDATION: {item['recommendation']}")
        print()

    # Print a compact summary table
    print("-" * 73)
    print("SUMMARY TABLE")
    print("-" * 73)
    print(f"{'Parameter':<22} {'Action':<25} {'Current Range':<25}")
    print("-" * 73)
    for item in needs_update:
        action = item['recommendation'].replace("Consider ", "")
        range_str = f"[{item['current_lo']:.2e}, {item['current_hi']:.2e}]"
        print(f"{item['param']:<22} {action:<25} {range_str:<25}")

print("\n" + "=" * 73)