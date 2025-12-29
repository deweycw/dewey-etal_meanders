from h5py import *
import numpy as np
import matplotlib.pyplot as plt
import sys
from pathlib import Path

# Add shared module to path (located in src/shared)
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent / 'src' / 'shared'))
import pflo

'''

Provide a data file including DEM in a column or row 

124 cells in length for mcp


works for x-sections
'''

def create_structred_grids(zz, dz, overall_domain_depth, bgs_soil):  #  resolution, zz -- elevation or DEM
    ny = 1
    nx = np.shape(zz)[0]
    overtop_null = 1.
    zz_size = np.shape(zz)[0]
    zz_max = np.floor(np.max(zz[1:zz_size]))+overtop_null # zz_size include cells for BC that are not used for max/min calculation
    zz_min = zz_max - overall_domain_depth # np.floor(np.min(zz[1:zz_size]))-(overall_domain_depth-overtop_null)
    zz_col = np.arange(zz_min, zz_max+dz, dz)
    nz = np.size(zz_col)

    gs_ref = np.mean(zz[:])
    
    #bgs_weathered_shale = 3.4
    print("\nref: ", gs_ref, "\nmax: ", zz_max, "\nmin: ", zz_min, "\nsoil: ",gs_ref - bgs_soil ) #,"\nshale: ",gs_ref - bgs_weathered_shale)

    mat_id  = np.ones((nx,nz))
    mat_id= mat_id.astype('int')
    mat_id_1d = np.reshape(mat_id,(nx*nz,1), order="F")

    bc_id  = np.ones((nx,nz))
    bc_id= bc_id.astype('int')
    bc_id_1d = np.reshape(bc_id,(nx*nz,1), order="F")

    face_id  = np.ones((nx,nz))
    face_id= face_id.astype('int')
    face_id_1d = np.reshape(face_id,(nx*nz,1), order="F")

    cell_id = np.reshape(np.arange(1, (nx*nz) +1),(nx,nz),order="F")
    cell_id= cell_id.astype('int')
    cell_id_1d = np.reshape(cell_id,(nx*nz, ),order="F")

    itop = 0
    for ii  in range(0, nx):  
        if ii < 1:
            # upstream bc
            bank_top = nz #int(1.7 / dz)  
            bc_id[ii,0:bank_top] = 8 # assign upstream BC cells
            face_id[ii,0:bank_top] = 3 # 
            #mat_id[ii,bank_top:np.size(zz_col)] = 0

        elif ii >= nx-1: 
            # downstream bc
            bank_top = nz #int(1.6/ dz)   
            bc_id[ii,0:bank_top] = 9 # assign downtstream (north) BC cells
            face_id[ii,0:bank_top] = 4 # assign west face to downstream BC 
            #mat_id[ii,bank_top:np.size(zz_col)] = 0
       
        if ii <= 30:
            fines_id = 2
        else:
            fines_id = 3
        print('nx %s, fines_id: %s' %(nx, fines_id))
        for  kk  in range(0, nz):
            if (zz_col[kk] - zz[ii] >= 0): # if above ground surface
                mat_id[ii, kk:np.size(zz_col)] = 0
                break
            elif (zz_col[kk] - zz[ii] <=0) and (zz_col[kk] - zz[ii] >= -0.1): # if at surface top layer
                kk_surface = int(kk + np.floor(0.1/dz))
                bc_id[ii, kk] = 91 + itop
                mat_id[ii, kk] = fines_id
                face_id[ii,kk] = 6 # assign top face to top US BC 
            elif ((zz_col[kk] - zz[ii] < 0) and (zz_col[kk] - (gs_ref - bgs_soil) > 0)): # if in soil layer 
                kk_surface = int(kk + np.floor(bgs_soil/dz))
                mat_id[ii, kk:kk_surface] = fines_id
        itop = itop + 1 

    mat_id_1d =  np.reshape(mat_id,(nx*nz, ),order="F")
    bc_id_1d =  np.reshape(bc_id,(nx*nz, ),order="F")
    face_id_1d =  np.reshape(face_id,(nx*nz, ),order="F")

    return mat_id_1d, cell_id_1d, face_id_1d,bc_id_1d,  nx, ny, nz, zz_min


def write_regions_files(mat_id_1d, cell_id_1d, face_id_1d, bc_id_1d, nx, output_dir):
    # find the indices of the BC cells
    # upstream BC
    upstream_bc_1d = pflo.find_cells(bc_id_1d, "equal", 8)
    upstream_bc_faces_1d = face_id_1d[upstream_bc_1d.astype('int')][...,None]
    upstream_bc_ids = cell_id_1d[upstream_bc_1d.astype('int')][...,None]

    # TOP  BCs
    top_bc_1d_list = [pflo.find_cells(bc_id_1d, "equal", 91 + itop) for itop in range(0, nx)]
    top_bc_faces_1d_list = [face_id_1d[top_bc_1d.astype('int')][...,None] for top_bc_1d in top_bc_1d_list]
    top_bc_ids_list= [cell_id_1d[top_bc_1d.astype('int')][...,None] for top_bc_1d in top_bc_1d_list]

    # downstream BC 
    downstream_bc_1d = pflo.find_cells(bc_id_1d,"equal",9)
    downstream_bc_faces_1d = face_id_1d[downstream_bc_1d.astype('int')][...,None]
    downstream_bc_ids = cell_id_1d[downstream_bc_1d.astype('int')][...,None]

    print("upstream_bc_ids: ", np.shape(upstream_bc_ids))
    print("downstream_bc_ids: ", np.shape(downstream_bc_ids))
    #print("top_bc_ids: ", np.shape(top_bc_ids))

    # create regions for .hd5 Region/Materials file
    upstream_bc = np.append(upstream_bc_ids, upstream_bc_faces_1d, axis=1)
    np.savetxt(output_dir / 'upstream_bc_reg.txt', upstream_bc, delimiter=' ')
    downstream_bc = np.append(downstream_bc_ids, downstream_bc_faces_1d, axis=1)
    np.savetxt(output_dir / 'downstream_bc_reg.txt', downstream_bc, delimiter=' ')

    itop = 0
    for top_bc_ids, top_bc_faces_1d in zip(top_bc_ids_list, top_bc_faces_1d_list):
        top_bc = np.append(top_bc_ids, top_bc_faces_1d, axis=1)
        fname = output_dir / f'top_bc_reg_{itop}.txt'
        np.savetxt(fname, top_bc, delimiter=' ')
        itop = itop + 1

    # soil reg
    soil_1d = pflo.find_cells(mat_id_1d, "equal", 2)
    soil_faces_1d = face_id_1d[soil_1d.astype('int')][..., None]
    soil_ids = cell_id_1d[soil_1d.astype('int')][..., None]

    # soil2 reg
    soil2_1d = pflo.find_cells(mat_id_1d, "equal", 3)
    soil2_faces_1d = face_id_1d[soil2_1d.astype('int')][..., None]
    soil2_ids = cell_id_1d[soil2_1d.astype('int')][..., None]

    # gravel reg
    gravel_1d = pflo.find_cells(mat_id_1d, "equal", 1)
    gravel_faces_1d = face_id_1d[gravel_1d.astype('int')][..., None]
    gravel_ids = cell_id_1d[gravel_1d.astype('int')][..., None]

    print("soil_ids: ", np.shape(soil_ids))
    print("soil2_ids: ", np.shape(soil2_ids))
    print("gravel_ids: ", np.shape(gravel_ids))

    soil = np.append(soil_ids, soil_faces_1d, axis=1)
    np.savetxt(output_dir / 'soil_reg.txt', soil, delimiter=' ')
    soil2 = np.append(soil2_ids, soil2_faces_1d, axis=1)
    np.savetxt(output_dir / 'soil2_reg.txt', soil2, delimiter=' ')
    gravel = np.append(gravel_ids, gravel_faces_1d, axis=1)
    np.savetxt(output_dir / 'gravel_reg.txt', gravel, delimiter=' ')



    h5_file_name = output_dir / 'xxgrid010-mzt-w-mc.h5'
    h5file = File(h5_file_name, mode='w')

    dataset_name = "/Materials/Cell Ids"
    h5dset = h5file.create_dataset(dataset_name, data=cell_id_1d, dtype=np.uint64)

    dataset_name = "/Materials/Material Ids"
    h5dset = h5file.create_dataset(dataset_name, data=mat_id_1d, dtype=np.uint64)

    region_group = h5file.create_group("Regions")

    n = np.shape(upstream_bc_faces_1d)[0]
    print('upstream:\t', n)
    filename = str(output_dir / 'upstream_bc_reg.txt')
    region_name = 'upstream_bc_reg'
    region = pflo.Region(region_group, region_name, filename)
    region.writeRegion(n)

    itop = 0
    for top_bc_faces_1d in top_bc_faces_1d_list:
        n = np.shape(top_bc_faces_1d)[0]
        filename = str(output_dir / f'top_bc_reg_{itop}.txt')
        region_name = f'top_bc_reg_{itop}'
        region = pflo.Region(region_group, region_name, filename)
        region.writeRegion(n)
        itop = itop + 1

    n = np.shape(downstream_bc_faces_1d)[0]
    print('dnstream:\t', n)
    filename = str(output_dir / 'downstream_bc_reg.txt')
    region_name = 'downstream_bc_reg'
    region = pflo.Region(region_group, region_name, filename)
    region.writeRegion(n)

    n = np.shape(soil_faces_1d)[0]
    n2 = np.shape(soil2_faces_1d)[0]
    print('soil, soil2:\t', n, n2)
    filename = str(output_dir / 'soil_reg.txt')
    filename2 = str(output_dir / 'soil2_reg.txt')
    region_name = 'soil_reg'
    region2_name = 'soil2_reg'
    region = pflo.Region(region_group, region_name, filename)
    region2 = pflo.Region(region_group, region2_name, filename2)
    region.writeRegion(n)
    region2.writeRegion(n2)

    n = np.shape(gravel_faces_1d)[0]
    print('gravel:\t', n)
    filename = str(output_dir / 'gravel_reg.txt')
    region_name = 'gravel_reg'
    region = pflo.Region(region_group, region_name, filename)
    region.writeRegion(n)

    h5file.close()

if __name__ == "__main__":
    # Use shared data directory (located in src/shared)
    SHARED_DATA_DIR = Path(__file__).parent.parent.parent.parent.parent / 'src' / 'shared' / 'data' / 'mzt'

    DEM = np.loadtxt(SHARED_DATA_DIR / 'MZT2.csv', delimiter=',')
    DEM = np.reshape(DEM, (np.size(DEM), 1), order="F")

    print(DEM)

    bgs_soil = 1.5  # m
    dz = 0.10
    overall_domain_depth = 2.5  # m

    [mat_id_1d, cell_id_1d, face_id_1d, bc_id_1d, nx, ny, nz, zz_min] = create_structred_grids(DEM, dz, overall_domain_depth, bgs_soil)

    write_regions_files(mat_id_1d, cell_id_1d, face_id_1d, bc_id_1d, nx, SHARED_DATA_DIR)

    print(ny, nx, nz)  



