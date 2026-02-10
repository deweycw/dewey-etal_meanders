"""
PFLOTRAN Structured Grid Generator for Cross-Sections

Generates structured grids with material and boundary condition assignments
for 2D cross-section models. Outputs HDF5 file with materials and regions.

PFLOTRAN Face Indices:
    WEST=1, EAST=2, SOUTH=3, NORTH=4, BOTTOM=5, TOP=6
"""

import argparse
from h5py import File
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch
import pflo

# Material IDs
MAT_INACTIVE = 0
MAT_GRAVEL = 1
MAT_SOIL = 2

# Boundary condition IDs
BC_UPSTREAM = 8
BC_DOWNSTREAM = 9
BC_TOP_START = 91  # Top BCs are numbered 91, 92, 93, ... for each column

# Face indices
FACE_WEST = 1
FACE_EAST = 2
FACE_SOUTH = 3
FACE_NORTH = 4
FACE_TOP = 6


def create_structured_grid(dem, dz, domain_depth, soil_depth, perp_axis='y'):
    """
    Create a structured grid from DEM elevations.

    Parameters
    ----------
    dem : array
        1D array of surface elevations along the transect
    dz : float
        Vertical cell size (m)
    domain_depth : float
        Total domain depth below max elevation (m)
    soil_depth : float
        Depth of soil layer below ground surface (m)
    perp_axis : str
        Axis perpendicular to flow ('y' = flow along x, 'x' = flow along y)

    Returns
    -------
    dict with grid arrays and dimensions
    """
    n_length = dem.shape[0]

    # Set grid dimensions and face orientations based on flow direction
    if perp_axis == 'y':
        nx, ny = n_length, 1
        us_face, ds_face = FACE_WEST, FACE_EAST
        flow_direction = "X (West to East)"
    else:
        nx, ny = 1, n_length
        ds_face, us_face = FACE_SOUTH, FACE_NORTH
        flow_direction = "Y (North to South)"

    # Calculate vertical extent
    buffer_above_surface = 1.0
    z_max = np.floor(np.max(dem[1:])) + buffer_above_surface
    z_min = z_max - domain_depth
    z_levels = np.arange(z_min, z_max + dz, dz)
    nz = len(z_levels)

    mean_elevation = np.mean(dem)
    soil_bottom = mean_elevation - soil_depth

    # Initialize arrays
    mat_id = np.ones((n_length, nz), dtype=int)
    bc_id = np.ones((n_length, nz), dtype=int)
    face_id = np.ones((n_length, nz), dtype=int)
    cell_id = np.arange(1, n_length * nz + 1).reshape((n_length, nz), order='F')

    # Assign materials and boundary conditions
    for ii in range(n_length):
        surface_elev = dem[ii]

        # Upstream boundary (first column)
        if ii == 0:
            bc_id[ii, :] = BC_UPSTREAM
            face_id[ii, :] = us_face

        # Downstream boundary (last column)
        elif ii == n_length - 1:
            bc_id[ii, :] = BC_DOWNSTREAM
            face_id[ii, :] = ds_face

        # Assign materials vertically
        for kk in range(nz):
            z = z_levels[kk]
            depth_below_surface = surface_elev - z

            if z >= surface_elev:
                # Above ground surface - inactive
                mat_id[ii, kk:] = MAT_INACTIVE
                break
            elif 0 < depth_below_surface <= 0.1:
                # Top cell - assign top BC
                bc_id[ii, kk] = BC_TOP_START + ii
                face_id[ii, kk] = FACE_TOP
                mat_id[ii, kk] = MAT_SOIL
            elif z > soil_bottom:
                # Within soil layer
                mat_id[ii, kk] = MAT_SOIL
            # else: remains MAT_GRAVEL (default)

    # Flatten arrays for output
    result = {
        'mat_id': mat_id.reshape(-1, order='F'),
        'cell_id': cell_id.reshape(-1, order='F'),
        'face_id': face_id.reshape(-1, order='F'),
        'bc_id': bc_id.reshape(-1, order='F'),
        'nx': nx,
        'ny': ny,
        'nz': nz,
        'z_min': z_min,
        'n_length': n_length,
    }

    # Print summary
    print("\n" + "="*50)
    print("GRID GENERATION SUMMARY")
    print("="*50)
    print(f"Flow direction:      {flow_direction}")
    print(f"Grid dimensions:     nx={nx}, ny={ny}, nz={nz}")
    print(f"Total cells:         {nx * ny * nz}")
    print(f"Transect length:     {n_length} cells")
    print(f"Vertical extent:     {z_min:.2f} to {z_max:.2f} m")
    print(f"Mean surface elev:   {mean_elevation:.2f} m")
    print(f"Soil bottom elev:    {soil_bottom:.2f} m")
    print(f"Upstream face:       {us_face} ({'WEST' if us_face == 1 else 'SOUTH'})")
    print(f"Downstream face:     {ds_face} ({'EAST' if ds_face == 2 else 'NORTH'})")

    return result


def write_regions_h5(grid, output_file="../xxgrid010-mc-cxc-top.h5"):
    """
    Write region and material data to HDF5 file for PFLOTRAN.

    Parameters
    ----------
    grid : dict
        Grid data from create_structured_grid()
    output_file : str
        Path to output HDF5 file
    """
    mat_id = grid['mat_id']
    cell_id = grid['cell_id']
    face_id = grid['face_id']
    bc_id = grid['bc_id']
    n_length = grid['n_length']

    print("\n" + "="*50)
    print("REGION ASSIGNMENT")
    print("="*50)

    # Find boundary condition cells
    upstream_idx = np.where(bc_id == BC_UPSTREAM)[0]
    downstream_idx = np.where(bc_id == BC_DOWNSTREAM)[0]

    # Find material cells
    soil_idx = np.where(mat_id == MAT_SOIL)[0]
    gravel_idx = np.where(mat_id == MAT_GRAVEL)[0]

    # Prepare region data
    regions = {
        'upstream_bc_reg': (upstream_idx, "Upstream BC"),
        'downstream_bc_reg': (downstream_idx, "Downstream BC"),
        'soil_reg': (soil_idx, "Soil"),
        'gravel_reg': (gravel_idx, "Gravel"),
    }

    # Add top BC regions
    top_regions = {}
    for i in range(n_length):
        idx = np.where(bc_id == BC_TOP_START + i)[0]
        if len(idx) > 0:
            top_regions[f'top_bc_reg_{i}'] = (idx, f"Top BC column {i}")

    # Print summary
    print(f"{'Region':<25} {'Cells':>10}")
    print("-" * 37)
    for name, (idx, desc) in regions.items():
        print(f"{desc:<25} {len(idx):>10}")
    print(f"{'Top BC regions':<25} {len(top_regions):>10}")

    # Write text files and collect data for HDF5
    region_data = {}

    for name, (idx, _) in {**regions, **top_regions}.items():
        cells = cell_id[idx].reshape(-1, 1)
        faces = face_id[idx].reshape(-1, 1)
        data = np.hstack([cells, faces])
        np.savetxt(f'{name}.txt', data, fmt='%d', delimiter=' ')
        region_data[name] = (cells, faces)

    # Write HDF5 file
    print(f"\nWriting HDF5: {output_file}")

    with File(output_file, mode='w') as h5:
        h5.create_dataset("/Materials/Cell Ids", data=cell_id, dtype=np.uint64)
        h5.create_dataset("/Materials/Material Ids", data=mat_id, dtype=np.uint64)

        region_group = h5.create_group("Regions")

        for name in region_data:
            n_cells = len(region_data[name][0])
            region = pflo.Region(region_group, name, f'{name}.txt', print=False)
            region.writeRegion(n_cells)

    print("Done.")


def visualize_grid(grid, dem, dz, domain_depth, perp_axis='y', save_path=None):
    """
    Create a visualization of the grid showing materials and boundary conditions.

    Parameters
    ----------
    grid : dict
        Grid data from create_structured_grid()
    dem : array
        Original DEM elevations
    dz : float
        Vertical cell size
    domain_depth : float
        Total domain depth
    perp_axis : str
        Axis perpendicular to flow ('y' = flow along x, 'x' = flow along y)
    save_path : str, optional
        Path to save figure (if None, displays interactively)
    """
    n_length = grid['n_length']
    nz = grid['nz']
    z_min = grid['z_min']

    # Determine axis labels based on flow direction
    if perp_axis == 'y':
        horiz_axis = 'X'
        us_face_name = 'WEST'
        ds_face_name = 'EAST'
    else:
        horiz_axis = 'Y'
        us_face_name = 'NORTH'
        ds_face_name = 'SOUTH'

    # Reshape arrays back to 2D for plotting
    mat_2d = grid['mat_id'].reshape((n_length, nz), order='F')
    bc_2d = grid['bc_id'].reshape((n_length, nz), order='F')

    # Create coordinate arrays
    x = np.arange(n_length)
    z = np.arange(z_min, z_min + nz * dz, dz)

    fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=True)

    # --- Plot 1: Materials ---
    ax1 = axes[0]

    # Custom colormap for materials
    mat_cmap = ListedColormap(['white', '#D2691E', '#8B4513'])  # inactive, gravel, soil
    mat_plot = ax1.pcolormesh(x, z[:mat_2d.shape[1]], mat_2d.T,
                               cmap=mat_cmap, vmin=0, vmax=2, shading='auto')

    # Overlay DEM surface
    ax1.plot(x, dem.flatten(), 'k-', linewidth=2, label='Ground surface')

    ax1.set_ylabel('Z (m)')
    ax1.set_title(f'Material Distribution ({horiz_axis}-Z Cross-Section)')

    # Legend for materials
    mat_legend = [
        Patch(facecolor='white', edgecolor='black', label='Inactive'),
        Patch(facecolor='#D2691E', label='Gravel'),
        Patch(facecolor='#8B4513', label='Soil'),
    ]
    ax1.legend(handles=mat_legend, loc='upper right')

    # --- Plot 2: Boundary Conditions ---
    ax2 = axes[1]

    # Create BC visualization array
    # 0=none, 1=upstream, 2=downstream, 3=top
    bc_viz = np.zeros_like(bc_2d)
    bc_viz[bc_2d == BC_UPSTREAM] = 1
    bc_viz[bc_2d == BC_DOWNSTREAM] = 2
    bc_viz[(bc_2d >= BC_TOP_START) & (bc_2d < BC_TOP_START + n_length)] = 3

    # Mask inactive cells
    bc_viz[mat_2d == MAT_INACTIVE] = -1

    bc_cmap = ListedColormap(['lightgray', 'white', 'blue', 'red', 'green'])
    bc_plot = ax2.pcolormesh(x, z[:bc_viz.shape[1]], bc_viz.T,
                              cmap=bc_cmap, vmin=-1, vmax=3, shading='auto')

    # Overlay DEM surface
    ax2.plot(x, dem.flatten(), 'k-', linewidth=2, label='Ground surface')

    ax2.set_xlabel(f'{horiz_axis} (cells)')
    ax2.set_ylabel('Z (m)')
    ax2.set_title('Boundary Conditions')

    # Legend for BCs
    bc_legend = [
        Patch(facecolor='lightgray', label='Inactive'),
        Patch(facecolor='white', edgecolor='black', label='Interior'),
        Patch(facecolor='blue', label='Upstream BC'),
        Patch(facecolor='red', label='Downstream BC'),
        Patch(facecolor='green', label='Top BC'),
    ]
    ax2.legend(handles=bc_legend, loc='upper right')

    # Add face labels
    us_face = FACE_WEST if perp_axis == 'y' else FACE_NORTH
    ds_face = FACE_EAST if perp_axis == 'y' else FACE_SOUTH
    ax2.annotate(f'{us_face_name} (Face {us_face})\nUpstream',
                 xy=(0, z.mean()), fontsize=9, ha='left', va='center',
                 bbox=dict(boxstyle='round', facecolor='lightblue'))
    ax2.annotate(f'{ds_face_name} (Face {ds_face})\nDownstream',
                 xy=(n_length-1, z.mean()), fontsize=9, ha='right', va='center',
                 bbox=dict(boxstyle='round', facecolor='lightcoral'))

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"Figure saved: {save_path}")
    else:
        plt.show()

    return fig, axes


def parse_args():
    parser = argparse.ArgumentParser(
        description='Generate PFLOTRAN structured grid from DEM cross-section',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument('--dem', default='MCP.csv',
                        help='Path to DEM CSV file')
    parser.add_argument('--dz', type=float, default=0.10,
                        help='Vertical cell size (m)')
    parser.add_argument('--depth', type=float, default=2.5,
                        help='Total domain depth (m)')
    parser.add_argument('--soil-depth', type=float, default=1.5,
                        help='Soil layer thickness (m)')
    parser.add_argument('--perp-axis', choices=['x', 'y'], default='y',
                        help='Axis perpendicular to flow (y=flow along x, x=flow along y)')
    parser.add_argument('--output', default='../xxgrid010-mc-cxc-top.h5',
                        help='Output HDF5 file path')
    parser.add_argument('--fig', default='grid_visualization.png',
                        help='Output figure path (use "none" to skip)')
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    print("="*50)
    print("PFLOTRAN GRID GENERATOR")
    print("="*50)
    print(f"DEM file:            {args.dem}")
    print(f"Vertical resolution: {args.dz} m")
    print(f"Domain depth:        {args.depth} m")
    print(f"Soil depth:          {args.soil_depth} m")
    print(f"Perpendicular axis:  {args.perp_axis}")
    print(f"Output HDF5:         {args.output}")

    # Load DEM
    dem = np.loadtxt(args.dem, delimiter=',').flatten()
    print(f"DEM points loaded:   {len(dem)}")
    print(f"Elevation range:     {dem.min():.2f} to {dem.max():.2f} m")

    # Generate grid
    grid = create_structured_grid(dem, args.dz, args.depth, args.soil_depth,
                                   perp_axis=args.perp_axis)

    # Write output files
    write_regions_h5(grid, output_file=args.output)

    # Visualize the grid
    if args.fig.lower() != 'none':
        visualize_grid(grid, dem, args.dz, args.depth,
                       perp_axis=args.perp_axis, save_path=args.fig)

    print("\n" + "="*50)
    print("COMPLETE")
    print("="*50)
