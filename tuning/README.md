# PFLOTRAN Parameter Tuning Workflow

This package provides tools for tuning PFLOTRAN reactive transport model parameters using sensitivity analysis and Bayesian optimization.

## Overview

The workflow offers multiple approaches:

1. **Sensitivity Analysis (Morris Method)**: Screen all 25 parameters to identify the most influential ones (~80-100 simulations)
2. **Bayesian Optimization**: Efficiently optimize the reduced parameter set using Gaussian Process surrogate modeling (~50-100 simulations)
3. **Agentic AI Workflow**: Use Claude to intelligently reason about results and make parameter adjustments based on biogeochemical understanding (~30 iterations)
4. **Validation**: Run final simulation with optimized parameters and generate diagnostic plots

## Agentic vs Traditional Optimization

| Aspect | Traditional (Bayesian) | Agentic (Claude) |
|--------|------------------------|------------------|
| Decision making | Fixed algorithm (EI acquisition) | AI reasons about each result |
| Domain knowledge | None (black-box) | Biogeochemistry understanding |
| Adaptability | Fixed exploration/exploitation | Adapts strategy based on learnings |
| Interpretability | Parameter values only | Explains reasoning and insights |
| Failure handling | Penalty value | Diagnoses cause, proposes fixes |

## Installation

### Requirements

```bash
pip install numpy pandas scipy scikit-learn pyyaml anthropic
```

### Environment Setup

Ensure PFLOTRAN is installed and the environment variable is set:
```bash
export PFLOTRAN_DIR=/path/to/pflotran
```

## Usage

### Command Line Interface

```bash
# Check that the chemistry template has correct $T markers
python -m tuning.main --phase check-template

# Run sensitivity analysis (Morris method)
python -m tuning.main --phase sensitivity \
    --meander mzt \
    --year 2019 \
    --n-trajectories 10 \
    --output-dir sensitivity_mzt_2019

# Run Bayesian optimization with influential parameters only
python -m tuning.main --phase optimize \
    --meander mzt \
    --year 2019 \
    --params-file sensitivity_mzt_2019/influential_parameters.json \
    --n-iter 50 \
    --output-dir optimize_mzt_2019

# Validate optimized parameters
python -m tuning.main --phase validate \
    --meander mzt \
    --year 2019 \
    --params-file optimize_mzt_2019/optimized_params.json \
    --output-dir validate_mzt_2019

# Run agentic AI workflow (recommended)
export ANTHROPIC_API_KEY=your_key_here
python -m tuning.main --phase agent \
    --meander mzt \
    --year 2019 \
    --n-iter 30 \
    --output-dir agent_mzt_2019
```

### Python API

```python
from tuning import (
    run_morris_analysis,
    run_bayesian_optimization,
    compute_objective_with_details
)

# Run sensitivity analysis
results = run_morris_analysis(
    year='2019',
    meander='mzt',
    n_trajectories=10
)

# Get influential parameters
influential_params = [r.parameter_name for r in results[:12]]  # Top 12

# Run optimization
opt_results = run_bayesian_optimization(
    year='2019',
    meander='mzt',
    param_names=influential_params,
    n_iterations=50
)

# Validate
validation = compute_objective_with_details(
    h5_path='path/to/results.h5',
    year='2019',
    meander='mzt'
)
```

## Configuration

### Simulation Configurations

| Config | nx | Start Date | Duration |
|--------|-----|------------|----------|
| mzt19 | 108 | 2019-04-19 | 3993 hours |
| mcp19 | 122 | 2019-04-19 | 3993 hours |
| mzt18 | 108 | 2018-05-01 | 5131 hours |
| mcp18 | 122 | 2018-05-01 | 5131 hours |

### Tunable Parameters

The workflow tunes 26 reaction parameters across these reaction blocks:

- **Root_Respiration**: 1 parameter (dissolution rate)
- **Fe++ oxidation**: 1 parameter (forward rate)
- **HS- oxidation**: 1 parameter (forward rate)
- **Aerobic respiration**: 3 parameters (rate constant, O2 and SOC half-saturation)
- **SOM_AC_FERMENTATION**: 2 parameters (rate, threshold)
- **FH_GT_MINERAL_RIPENING**: 1 parameter (ripening rate)
- **JINBETHKE_NITRATE_ACETATE**: 4 parameters (RMAX, K_DONOR, K_ACCEPTOR, O2_THRESHOLD)
- **JINBETHKE_FERRIHYDRITE_ACETATE**: 4 parameters
- **JINBETHKE_GOETHITE_ACETATE**: 4 parameters
- **JINBETHKE_SULFATE_ACETATE**: 4 parameters

### Species Weights

The objective function uses these weights for each species:

| Species | Weight | Description |
|---------|--------|-------------|
| TIC | 1.0 | Total Inorganic Carbon |
| pH | 1.0 | pH |
| Ca | 0.8 | Calcium |
| Fe | 0.8 | Iron |
| SO4 | 0.7 | Sulfate |
| NPOC | 0.6 | Non-purgeable Organic Carbon |
| NO3 | 0.3 | Nitrate (sparse) |
| DO | 0.3 | Dissolved Oxygen (sparse) |

## Output Files

### Sensitivity Analysis

```
sensitivity_mzt_2019/
├── checkpoint.json           # Progress checkpoint (for resuming)
├── morris_results.json       # Full results with elementary effects
├── morris_results.csv        # Summary table
└── influential_parameters.json  # Top influential parameter names
```

### Optimization

```
optimize_mzt_2019/
├── checkpoint.json           # Progress checkpoint
├── optimization_history.csv  # All iterations with objectives
└── optimized_params.json     # Best parameter values
```

### Validation

```
validate_mzt_2019/
├── validation_results.json   # Detailed validation metrics
└── [simulation files]        # PFLOTRAN output files
```

## Template Markers

The chemistry template (`TEMPLATE-chemistry.txt`) uses `$T` markers to identify tunable parameters:

```
Root_Respiration
  $T DISSOLUTION_RATE_CONSTANT -12.1d0
  PRECIPITATION_RATE_CONSTANT 0.d0
/
```

The `$T` marker must appear at the beginning of the line (after indentation) before the parameter keyword.

## Resuming Interrupted Runs

Both sensitivity analysis and optimization support checkpointing:

```bash
# Resume sensitivity analysis
python -m tuning.main --phase sensitivity \
    --resume sensitivity_mzt_2019/checkpoint.json

# Resume optimization
python -m tuning.main --phase optimize \
    --resume optimize_mzt_2019/checkpoint.json
```

## Agentic AI Workflow

The agentic workflow uses Claude to intelligently reason about simulation results and make parameter adjustments. Unlike traditional optimization:

### How It Works

1. **Run simulation** with current parameters
2. **Analyze results**: Claude examines per-species KGE metrics
3. **Diagnose issues**: Identifies which aspects of the model are performing poorly
4. **Reason about parameters**: Uses biogeochemical knowledge to determine which parameters likely control the poorly-performing species
5. **Propose adjustments**: Suggests specific parameter changes with scientific justification
6. **Learn and adapt**: Records insights and adapts strategy over iterations

### Example Agent Reasoning

```
Diagnosis: TIC is overpredicted (KGE=0.42) while Fe++ is underpredicted (KGE=0.31).
High TIC suggests excessive CO2 production from root respiration or aerobic processes.
Low Fe++ indicates iron reduction may be too slow or inhibited.

Reasoning: The O2_THRESHOLD for iron reduction (1e-5) may be too low, preventing
Fe(III) reduction from occurring even when conditions should be anoxic.
Additionally, the root respiration rate may be too high.

Adjustments:
- ferrihydrite_o2_threshold: 1e-5 → 5e-5 (allow Fe reduction at higher O2)
- root_respiration_dissolution_rate: 7.9e-13 → 3e-13 (reduce CO2 production)

Insight: O2 threshold parameters are critical for controlling the transition
between aerobic and anaerobic metabolisms in the hyporheic zone.
```

### Output Files

```
agent_mzt_2019/
├── checkpoint.json           # Agent state for resuming
├── final_results.json        # Complete results with history
├── best_params.json          # Optimized parameter values
└── insights.md               # Key learnings from the agent
```

## Expected Runtime

- **Single simulation**: ~30-45 minutes (spin-up + transient)
- **Sensitivity analysis** (80 simulations): ~2-3 days
- **Bayesian optimization** (50 iterations): ~1-2 days
- **Agentic workflow** (30 iterations): ~15-20 hours
- **Total traditional workflow**: ~4-5 days
- **Agentic-only workflow**: ~15-20 hours (more efficient due to intelligent decisions)

## Troubleshooting

### Simulation Failures

PFLOTRAN can fail due to chemistry solver divergence. The workflow:
- Automatically assigns a penalty objective value (2.0)
- Logs the failure and continues
- Saves checkpoints for resuming

Check `tuning.log` for detailed error messages.

### Memory Issues

For large grids, ensure sufficient memory is available. The MZT grid (108 cells) typically requires ~4-8 GB RAM per PFLOTRAN process.

### Convergence Issues

If optimization doesn't converge:
1. Increase `--n-iter` for more iterations
2. Increase `--n-initial` for better initial GP fit
3. Check if parameter bounds are appropriate

## References

- Morris, M.D. (1991). Factorial Sampling Plans for Preliminary Computational Experiments. Technometrics, 33(2), 161-174.
- Snoek, J., Larochelle, H., & Adams, R.P. (2012). Practical Bayesian Optimization of Machine Learning Algorithms. NeurIPS.
- Gupta, H.V., Kling, H., Yilmaz, K.K., & Martinez, G.F. (2009). Decomposition of the mean squared error and NSE performance criteria: Implications for improving hydrological modelling. Journal of Hydrology, 377(1-2), 80-91.
