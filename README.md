# Lateral DIC Exports from Floodplain Soils

Code and simulation files for Dewey et al. manuscript on lateral dissolved inorganic carbon (DIC) exports from floodplain soils.

## Directory Structure

```
├── data/
│   ├── observational/
│   │   ├── field/          # Field measurements
│   │   └── lab/            # Lab measurements
│   └── model_output/       # PFLOTRAN simulation results
├── figures/                # Generated figures for manuscript
├── src/
│   ├── processing/         # Data processing scripts
│   ├── figures/            # Figure generation code
│   └── sensitivity/        # Sensitivity analysis code
├── pflotran/
│   ├── input/              # PFLOTRAN input files
│   ├── templates/          # Reusable input file templates
│   └── scripts/            # Automation scripts for runs
├── notebooks/              # Jupyter notebooks for exploration
└── results/                # Processed results and summaries
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

[Add instructions for running simulations and generating figures]

## Citation

[Add citation when available]

## License

[Add license information]
