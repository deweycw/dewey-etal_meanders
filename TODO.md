# TODO

## pflotran_generator.py
- [ ] Sync changes between mzt19/ and mcp19/ versions
- [ ] Verify hydro file paths for all year/meander combinations
- [ ] Test all 4 configurations (mzt/2018, mzt/2019, mcp/2018, mcp/2019)
- [ ] Move pflotran_generator.py outside of individual simulation folders & copy version into simulation folder 

## pflotran.py (PflotranProcessor)
- [ ] Fix `plot_validation()` - verify mask indexing works correctly
- [ ] Add unit tests for unit conversion functions
- [ ] Document COMPONENT_TO_OBS_MAP mappings

## Simulations
- [ ] create simulation dirs for 2018 for both meanders 
- [ ] run simulations for 2018
- [ ] check TEMPLATE files and consider central location for them 
- [ ] tune params for MCP model & examine original model out

## Figures
- [ ] Finalize validation plots in one-to-one_dev.ipynb
- [ ] Complete 1-to-1 figure with both years 

## Data Processing
- [ ] Verify observation data file formats
- [ ] Check datetime handling for all meander/year combinations

## Documentation
- [ ] Update README with current workflow
- [ ] Document pflotran_generator.py usage and arguments

---
Last updated: 2025-12-29
