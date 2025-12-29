# PFLOTRAN Build Log

---

## 2025-12-27: Initial Directory Structure and Script Setup

### 1. Directory Structure Created
Set up `pflotran/build/` with organized subdirectories:
```
pflotran/build/
├── shared/           # Common utilities and consolidated data
│   ├── pflo.py       # Core PFLOTRAN utility module
│   ├── __init__.py
│   └── data/mzt/     # Consolidated MZT data files
├── mcp/              # Meander cutoff point scripts
│   ├── scripts/
│   └── data/
├── mzt/              # MZT domain scripts
│   ├── scripts/
│   └── data/
├── mzt-w-mc/         # MZT with mud cap scripts
│   ├── scripts/
│   └── data/
├── bcs/              # Boundary condition files
└── transient-input/  # Transient BC input scripts
    ├── mcp-18/, mcp-19/
    ├── mzt-18/, mzt-19/
    └── mzt-18-no-dam/
```

### 2. Scripts Copied and Enhanced
Copied build scripts from `/Users/christiandewey/Code/dewey-etal-meanders/simulations/co2/build-scripts` and applied fixes:

**Import path fixes** - Added `sys.path` manipulation for shared module:
```python
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'shared'))
import pflo
```

**Code fixes applied to all scripts:**
- Fixed deprecated string comparisons: `is 'above'` → `== 'above'`
- Fixed global variable issues: added `nx` parameter to `write_regions_files()`
- Fixed hardcoded absolute paths → relative paths using `Path(__file__)`
- Fixed bare except clauses → specific exception types

### 3. Data Consolidation
**Before:** MZT data duplicated in `mzt/data/` and `mzt-w-mc/data/`

**After:** Single source of truth at `shared/data/mzt/` containing:
- `MZT2.csv` (input DEM)
- Region files: `upstream_bc_reg.txt`, `downstream_bc_reg.txt`, `soil_reg.txt`, `gravel_reg.txt`
- 108 top BC region files: `top_bc_reg_0.txt` through `top_bc_reg_107.txt`

**Scripts updated to use shared data:**
- `mzt/scripts/str_grid-2-MZT-top-bc.py`
- `mzt-w-mc/scripts/str_grid-2-MZT-w-MC.py`
- `mzt-w-mc/scripts/str_grid-2-MZT-w-MC-c.py`

### 4. Cleanup
**Removed:**
- Duplicate data files from `mzt/data/` and `mzt-w-mc/data/`
- Excel temp file `~$bc_2018_master.xlsx`
- `.DS_Store` files
- Accidental copy files (`pflotran-sim-TEMP-chunk1 copy.in`)

**Created:**
- `requirements.txt` with dependencies: numpy, pandas, h5py, matplotlib, scipy
- Updated `.gitignore` with `~$*` pattern for Office temp files
