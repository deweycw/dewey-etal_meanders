# PFLOTRAN

Reactive transport model files.

- **input/** - PFLOTRAN input files (.in)
- **templates/** - Reusable input file templates for parameter sweeps
- **scripts/** - Bash/shell scripts for automated simulation runs
- **build/** - Python build scripts for creating PFLOTRAN input files
  - **shared/** - Common utility modules (e.g., `pflo.py`)
  - **mcp/** - Meander cutoff point (MCP) domain
    - `scripts/` - Grid and BC build scripts
    - `data/` - DEMs, region files, CSVs
  - **mzt/** - MZT domain
    - `scripts/` - Grid and BC build scripts
    - `data/` - DEMs, region files, CSVs
  - **mzt-w-mc/** - MZT with meander cutoff domain
    - `scripts/` - Grid and BC build scripts
    - `data/` - DEMs, region files, CSVs
  - **bcs/** - Boundary condition files
  - **transient-input/** - Transient hydro/chem boundary condition inputs
