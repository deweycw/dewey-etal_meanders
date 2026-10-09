# Lateral DIC Exports from Floodplain Soils

Code and simulation files for Dewey et al. manuscript on lateral dissolved inorganic carbon (DIC) exports from floodplain soils.

## Directory Structure

```
├── data/
│   ├── observational/          # Field/lab data: porewater, river-chem, river-stage,
│   │                           #   gw-elevs-{c,z}, solid-phase-chem, locs.csv
│   └── model_output/           # PFLOTRAN simulation results
├── pflotran/
│   ├── build-code/             # One-time grid, region, and BC build scripts
│   │   ├── mcp/, mzt/, mzt-w-mc/   # Per-domain grid scripts + data
│   │   └── transient-input/    # Original transient input builders (per meander/year)
│   └── simulations/
│       ├── pflotran_generator.py   # Current input-file generator
│       ├── TEMPLATE-*.in/.txt  # Shared input, chemistry, and constraint templates
│       ├── hydro-bcs/          # River-stage boundary condition files
│       ├── chem-bcs/           # River chemistry boundary condition CSVs
│       ├── xxgrid010-*.h5      # MCP (mc) and MZT (mz) grids
│       └── {mcp,mzt}{18,19}/   # Generated runs (<date>/<datetime>/) + legacy scripts
├── calibration/                # Manual calibration runs (run_<id>/), shared/<cfg>/ inputs
│                               #   for non-MCP19 configs, helper scripts, tuning_log.csv
├── sensitivity/                # Morris sensitivity runs (run000–run339), SLURM scripts,
│                               #   analysis_results/
├── tuning/                     # Automated tuning package (python -m tuning.main)
├── src/
│   ├── processing/             # Output processing (PflotranProcessor, unit conversions)
│   ├── figures/                # Figure generation code
│   ├── sensitivity/            # Morris trajectory creation, extraction, analysis
│   └── shared/                 # Shared utilities (pflo.py) and MZT data
├── figures/                    # Generated figures for manuscript
├── notebooks/                  # Jupyter notebooks for exploration
├── results/                    # Processed results and summaries
├── singularity.def             # Post-processing container (pflotran-postproc.sif)
└── verification_script.sh      # Local MPI scaling benchmark
```

## Requirements

- Python 3.13+
- PFLOTRAN
- See `requirements.txt` for Python dependencies

## Setup

```bash
python -m venv env
source env/bin/activate
pip install -r requirements.txt
```

## Usage

### Overview

Every simulation is a two-stage PFLOTRAN run:

1. **Spin-up** (`*_spin.in`): 0.5 y with steady boundary conditions. PFLOTRAN writes `<basename>_spin-restart.chk` when it finishes.
2. **Transient** (`*.in`): restarts from the spin-up checkpoint and runs 3993 h (2019) or 5131 h (2018). It is driven by hourly river-stage files and per-column top-boundary files in `trans-top-bcs/` (122 columns for MCP, 108 for MZT).

Both stages are run with:

```bash
mpirun -np <N> $PFLOTRAN_EXE -pflotranin <file>.in
```

Locally, `PFLOTRAN_EXE` is `~/Code/pflotran/src/pflotran/pflotran`. On the cluster, PFLOTRAN runs inside a Singularity image.

| Config | Meander | nx | Start date | Duration |
|--------|---------|-----|------------|----------|
| mzt19 | MZT | 108 | 2019-04-21 | 3993 h |
| mcp19 | MCP | 122 | 2019-04-21 | 3993 h |
| mzt18 | MZT | 108 | 2018-04-01 | 5131 h |
| mcp18 | MCP | 122 | 2018-04-01 | 5131 h |

### 1. Generate input files

`pflotran/build-code/` holds the one-time scripts that built the grids, regions, and boundary files. Rerun them only to change the domain.

`pflotran/simulations/pflotran_generator.py` builds spin-up and transient input files from the shared templates and boundary-condition data:

```bash
cd pflotran/simulations
python pflotran_generator.py --year 2019 --meander mcp   # --meander mzt, --year 2018
```

- Inputs: `TEMPLATE-pflotran{,-spin}.in`, `TEMPLATE-chemistry.txt`, `TEMPLATE-constraint.txt`, `hydro-bcs/`, `chem-bcs/`, and the grid files `xxgrid010-{mc,mz}-cxc-top.h5`.
- Output: `<meander><yy>/<date>/<datetime>/`, containing both `.in` files, `trans-top-bcs/`, river and top chemistry constraints, copies of the BC files, and `generation.log`.
- The transient file's restart `FILENAME` is set to the matching spin-up checkpoint automatically.
- `$T` tuning markers are stripped from the chemistry block unless `--keep-tuning-markers` is passed (needed for `tuning/`).
- River-stage files in `hydro-bcs/` are in each grid's model coordinates: MZT z = m ASL − 2721.5 (logger data in `data/observational/river-stage/z_river_elevs_ALL.csv`), MCP z = m ASL − 2757.5. The MZT files were shifted −0.30 m on 2026-10-09 to match the MZT grid (they had used 2721.2). There is no stage logger at MCP: `hydro-bcs/make_mcp_stage.py` builds the MCP files from the MZT record in absolute elevations (MCP upstream = MZT upstream + 36.30 m; MCP head drop = (MZT drop + 0.6 m) × 61/52), using the MZT no-dam record for 2018. It supersedes the MCP cells of `dwn_bc_creator_MC.ipynb`.
- Per-configuration settings (nx, heads, BC files, duration) are in `SIMULATION_CONFIGS`. Simulation start dates are in `YEAR_CONFIGS` and must match t=0 of the hydro BC files (2018-04-01, 2019-04-21). Copies of the generator inside `mcp18/`, `mzt19/`, etc. are older versions.
- The templates match calibration run `manual_cal027`: regenerated MCP 2019 inputs are identical to it apart from paths and run IDs, two intentional fixes (river/top chemistry now aligned to 2019-04-21 rather than 2019-04-19, and the spin-up downstream head taken from `SIMULATION_CONFIGS`, 0.91 vs 0.907 m). If the model changes in the calibration runs, port the changes back to the templates.

### 2. Manual calibration (`calibration/`)

Every calibration script takes `--meander mcp|mzt` and `--year 2018|2019`, defaulting to MCP 2019. MZT 2018 also takes `--scenario dam|nodam` (default `dam`): a beaver dam raised the upstream river level from 2018-07-28, and the no-dam scenario holds the head drop at its 07-28 value after that date. Run all commands from `calibration/`. In the examples, `M` is the meander, `Y` the year, and `<cfg>` is `M` plus the 2-digit year (e.g. `mzt18`), with `nd` appended for the no-dam scenario (`mzt18nd`).

| Config | Run files | Shared inputs (grid, river stage, `trans-top-bcs/`, `hanford-cd.dat`) |
|--------|-----------|------------------------------------------------------------|
| MCP 2019 | `run_<id>/pflotran-mcp19_<id>{_spin,}.in` | `calibration/` (referenced as `../`) |
| MCP 2018, MZT 2018 (dam / no-dam), MZT 2019 | `run_<id>/pflotran-<cfg>_<id>{_spin,}.in` | `calibration/shared/<cfg>/` (created by `init_run.sh`) |

**Step 0: create the first run for a new configuration (once per meander/year).** Skip this for MCP 2019, which already has a run history (`run_manual_cal*`).

```bash
./init_run.sh mzt18_cal000 --meander mzt --year 2018
./init_run.sh mzt18nd_cal000 --meander mzt --year 2018 --scenario nodam   # separate no-dam run
```

This runs `pflotran_generator.py` for that meander/year. It copies the grid and boundary files once to `shared/<cfg>/`, and puts the renamed spin/transient `.in` files in `run_mzt18_cal000/` with every file path pointing at `shared/<cfg>/`. It also sets the restart `FILENAME` and checks that every referenced file exists. The templates hold the `manual_cal027` model (chemistry, materials, initial minerals, 0.5 y spin-up). To start from a later calibration instead, add `--chemistry-from run_<id>`, which copies that run's CHEMISTRY block (reaction network and parameter values). To reuse generator output you already have, pass `--from <generator_output_dir>` instead of rerunning the generator.

**Step 1: clone the previous run.**

```bash
./new_run.sh run_mzt18_cal001 run_mzt18_cal000
```

This copies the `.in` files, renames them to the new run ID, and points the transient restart at the new run's spin-up checkpoint.

**Step 2: set the parameters.** Edit the reaction parameters in **both** `_spin.in` and the transient `.in`, then confirm the two CHEMISTRY blocks still match:

```bash
python check_chemistry.py run_mzt18_cal001
```

**Step 3: run the model** (spin-up, check for the checkpoint, then transient; 8 MPI ranks, about 30–45 min):

```bash
./submit.sh mzt18_cal001 --meander mzt --year 2018
```

Failures are logged to `run_<id>/failed_runs.log`.

**Step 4: evaluate and log.**

```bash
python evaluate_run.py mzt18_cal001 --meander mzt --year 2018 --note "what changed"
```

This extracts the tuned parameters, computes per-species KGE/NSE/RMSE against `data/observational/porewater/<mc|mz>_<year>_porewater.csv`, and appends a row to `tuning_log.csv` (marked `[REPEAT]` if the parameters match an earlier row). It also saves spin/transient time-series and 1:1 validation PNGs to the run directory. Options: `--no5` also scores without well 5D, `--no-log`/`--no-plots` skip those steps, and `--obs` picks a different observation file. `check_calibration_results.ipynb` (MCP 2019) does the same interactively and adds cross-section plots.

**Step 5: compare and repeat.** Compare `KGE_mean` and per-species KGE in `tuning_log.csv`, then return to Step 1, cloning the best run so far. Once a run is evaluated, `./clean_runs.sh run_<id>` deletes its `.h5`/`.out` output. Evaluate before cleaning: `evaluate_run.py` reads the `.h5` files.

For MCP 2019, drop the `--meander`/`--year` flags:

```bash
./new_run.sh run_manual_cal028 run_manual_cal027
python check_chemistry.py run_manual_cal028
./submit.sh manual_cal028
python evaluate_run.py manual_cal028 --note "what changed"
```

### 3. Morris sensitivity analysis (`sensitivity/`, HPC)

1. `src/sensitivity/create-morris-trajectories.ipynb` samples 16 parameters with SALib (340 runs, written to `morris_parameter_sets.csv`). It copies `sensitivity/run_template/` to `run000`–`run339` and fills in the `{{param}}` placeholders.
2. Copy `sensitivity/` to the cluster (`/lustre/dewey/users/4315/sensitivity`) and submit the SLURM array:
   ```bash
   sbatch submit.sh   # 340 tasks, up to 64 concurrent, 4 ranks each, PFLOTRAN in pflotran.sif
   ```
3. Resubmit incomplete runs. These scripts find runs whose `.h5` output is too small and submit themselves as an array job:
   ```bash
   bash submit_spin_trans.sh   # spin-up incomplete -> rerun spin + transient
   bash submit_trans_only.sh   # spin-up complete, transient incomplete
   ```
   `check_runs.sh`, `detect_failures.sh`, and `diagnose_failures.py` help with triage.
4. Extract objective-function values with `sbatch src/sensitivity/submit_extract.sh`. It runs `extract_sa_results.py` inside `pflotran-postproc.sif`, which is built from `singularity.def`.
5. Analyze with `src/sensitivity/morris-analysis.ipynb`. Output goes to `sensitivity/analysis_results/`.

### 4. Automated tuning (`tuning/`)

Morris screening, Bayesian optimization, and an LLM-driven tuning loop, run via `python -m tuning.main --phase ...`. Requires `PFLOTRAN_DIR`. See [`tuning/README.md`](tuning/README.md).

### 5. Legacy one-command scripts

`pflotran/simulations/{mzt19,mcp19}/run2d.sh` (and `run1d.sh`) generate inputs, run spin-up and transient with 12 ranks, and plot with `obs_v_sim.py`. `mcp19/run2d.sh` is out of date: it calls `xsection-make-mzt19-input.py`, which doesn't exist in that folder.

### Notes

- Hard-coded paths differ by machine: `/Users/christiandewey/...` (Mac) in the notebooks, `/home/christiandewey/...` in the local scripts, and `/lustre/...` on the cluster. Update them before running elsewhere.
- Local MPI scaling (`benchmark_results.txt`, from `verification_script.sh`): 14 ranks was fastest. The 16- and 20-rank runs crashed.

## Citation

[Add citation when available]

## License

[Add license information]
