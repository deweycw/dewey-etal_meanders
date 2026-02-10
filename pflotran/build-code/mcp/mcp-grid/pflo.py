import os
import sys
import numpy as np
import matplotlib.pyplot as plt 
import scipy
import csv
import glob
import shutil
from datetime import datetime, date, time
from h5py import *
import h5py
import re
import matplotlib.pyplot as plt
from io import StringIO   # StringIO behaves like a file object
import math
'''
THIS MODULE CONTAINS FUNCTIONS POTENTIALLY USEFULF FOR MODIFYING DATA FOR PFLOTRAN SIMULATIONS
'''

def get_distance(list1, list2):
	'''
	This function finds the distance between points in a matrix. The coordinates are the row and col indices. 

	list1:  {numpy array}  [[row_1a,col_1a],...,[row_na,col_na]] np array of points
	list2:  {numpy array}  [[row_1b,col_1b],...,[row_nb,col_nb]] np array of points

	returns: {list}: list of points and distances assoviated wtih points
				e.g. 
					[[([x1,y1], [x2,y2]),d1] 
	   				 [([x1,y1], [x3,y3]),d2]]
	   			where [x1,y1] is the ref point
	'''

	len1 = len(list1)
	len2 = len(list2)
	distance = []

	for l1 in range(0,len1):
		for l2 in range(0,len2):
			distance.append([([list1[l1][0],list1[l1][1]], [list2[l2][0],list2[l2][1]]), math.sqrt((list1[l1][0]-list2[l2][0])**2 + (list1[l1][1]-list2[l2][1])**2)])

	return distance


 
def make_pflo_mat(vec,dim):
	'''
	This function takes a 1D vector and converts it to a matrix of specified size. 
	For a matrix M of size (r,c), elements are added as follows:

		M[r][0], M[r][1], ... , M[r][c-1], M[r][c]
		M[r-1][0], M[r-1][1], ... , M[r-1][c-1], M[r-1][c]
		.
		.
		.
		M[1][0], M[1][1], ... , M[1][c-1], M[1][c]
		M[0][0], M[0][1], ... , M[0][c-1], M[0][c]

	Population is performed in this way so that material ID vectors for PFLOTRAN can be tested for correct order. 

	vec:     {numpy.array}  1D array (vertical)
	dim:     {tuple}        tuple with specified dimensions of target matrix (rows, cols); user needs to insure that dimensions are possible for 'vec'
	return:  {numpy.array}  2D array with shape = dim
	'''

	i = 0
	rows = dim[0]
	cols = dim[1]
	mat = np.zeros(dim)
	for rr in range(rows,0,-1):
		for cc in range(0,cols):
			mat[rr-1,cc] = vec[i]
			i = i + 1
	mat = mat.astype('float')	
	return mat

def make_3d_mat(vec,dim):
    '''
    This function takes a 1D vector and converts it to a 3D matrix of specified size. 
    For a matrix M of size (r,c), elements are added as follows:

        M[r][0], M[r][1], ... , M[r][c-1], M[r][c]
        M[r-1][0], M[r-1][1], ... , M[r-1][c-1], M[r-1][c]
        .
        .
        .
        M[1][0], M[1][1], ... , M[1][c-1], M[1][c]
        M[0][0], M[0][1], ... , M[0][c-1], M[0][c]

    Population is performed in this way so that material ID vectors for PFLOTRAN can be tested for correct order. 

    vec:     {numpy.array}  1D array (vertical)
    dim:     {tuple}        tuple with specified dimensions of target matrix (rows, cols, nz); user needs to insure that dimensions are possible for 'vec'
    return:  {numpy.array}  3D array with shape = dim
    '''

    cc = 0
    rows = dim[0]
    cols = dim[1]
    nz = dim[2]
    mat = np.zeros(dim)
    for jj in range(0,cols):    
        for kk in range(nz,0,-1):    
            for ii in range(rows,0,-1):
                mat[ii-1,jj,kk-1] = vec[cc]
                cc += 1
    mat = mat.astype('float')   
    return mat

# Region object
class Region:
  def __init__(self,region_group,region_name,filename,print=True):
    self.region_name = region_name
    self.filename = filename
    self.print = print
    self.group = region_group.create_group(self.region_name)
  def writeRegion(self,n):
    # in text file, region data should be specified as follows
    # cell_id face_id
    # one connection per line
    cell_id_array = np.zeros(n,'=i4')
    face_id_array = np.zeros(n,'=i4')
    f = open(self.filename)
    count = 0
    while (1):
      s = f.readline()
      if len(s) < 2:
        break
      w = s.split()
      cell_id_array[count] = int(float(w[0]))
      face_id_array[count] = int(float(w[1]))
      count += 1
    iarray = np.zeros(count,'=i4')
    iarray[0:count] = cell_id_array[0:count]
    dataset_name = 'Cell Ids'
    if self.print:
        print('i: ',np.shape(iarray))
    self.group.create_dataset(dataset_name, data=iarray)
    cell_id_array = 0
    iarray[0:count] = face_id_array[0:count]
    dataset_name = 'Face Ids'
    self.group.create_dataset(dataset_name, data=iarray)
    face_id_array = 0
    iarray = 0
    if self.print:
        print('done with Region:', self.region_name)



def assign_inactive(elev,domain):
    '''
    elev: float specifying elevation criterion for assignment of active cells; cells with elevation below this criterion will be inactive
    domain: 2D matrix of DEM data 
    
    returns:
    '''

    nx = np.shape(domain)[1] # number of cols is number of cells in X-dir
    ny = np.shape(domain)[0] # number of rows is number of cells in Y-dir
    mat_id  = np.ones((ny,nx))  # matrix of cell ids; same size as domain
    print(np.shape(mat_id))
    mat_id= mat_id.astype('int')

    for xx in range(0,nx):
        for yy in range(0,ny):
            if domain[yy,xx] < elev:
                mat_id[yy,xx] = 0
    return mat_id



def deactivate_range(points,dir,mat_id):
    '''Given a two points that define a line cutting the domain, assign values of 0 to all cells above or below the line 
    line: two points in domain [[x1,y1],[x2,y2]], where x2 is greater than x1 (y1, y2 are the Y-coords associated with those X-coords); NOTE: origin is top-left --> Y increases downward
    dir: {string} 'above' or 'below'; 1 will deactivate above line; 0 deactivates below line 
    mat_id: matrix of material ids, same size as domain 
    return: matrix with deactivated cells 
    '''
    x1 = points[0][0]
    x2 = points[1][0]
    y1 = points[0][1]
    y2 = points[1][1]
    nx = np.absolute(x2 - x1)
    ny = np.absolute(y2 - y1)
    yl = np.shape(mat_id)[0]
    m = -(y2-y1)/(x2-x1)
    m = np.ceil(1/m)
    sign = np.absolute(m)/m
    dstep = 1
    dy = 0
    if dir is 'above':
        for xx in range(x1,x2):
            for yy in range(0, int(y1 + dy)):
                mat_id[yy,xx] = 0
            if  dstep % m == 0:
                dy = dy - sign
            dstep = dstep + 1
    elif dir is 'below':
        for xx in range(x1,x2):
            for yy in range(int(y1 + dy),yl):
                mat_id[yy,xx] = 0
            if  dstep % m == 0:
                dy = dy - sign
            dstep = dstep + 1
    return mat_id

def assign_BC_cells(mat_id, idn):
    '''
    assigns cells around active cells an ID which can be used to define the boundary condition zone

    mat_id: matrix of material ids, same dims as domain 
    idn: {int} integer to be used as cell ID
    return: [matrix of cell IDs with BC cells identified, matrix of face vals for BCs,array of coords of BC cells]
    '''
    nx = np.shape(mat_id)[1]
    ny = np.shape(mat_id)[0]
    faces = np.zeros_like(mat_id)
    coords = []
    cellid = []

    for xx in range(0, int(nx)):
        for yy in range(0, int(ny)):
            if mat_id[yy,xx] == 1 and mat_id[yy-1,xx] == 0: # inactive cells above
                if yy == 0:     
                    mat_id[yy,xx] = idn+2
                    faces[yy,xx] = 3 #south face
                    coords.append([yy,xx,1])
                    #cellid.append([nx*ny])
                else:
                    mat_id[yy-1,xx] = idn
                    faces[yy-1,xx] = 4 #north face
                    coords.append([yy-1,xx,1])
                    #cellid.append([xx*yy])
            if mat_id[yy,xx] == 0 and mat_id[yy-1,xx] == 1: # inactive cells below
                mat_id[yy,xx] = idn
                faces[yy,xx] = 3 #south face
                coords.append([yy,xx,1])
                #cellid.append([xx*yy])
            if mat_id[yy,xx] == 1 and mat_id[yy,xx-1] == 0: # inactive cells to left
                if xx == 0: 
                    mat_id[yy,xx] = idn+2
                    faces[yy,xx] = 2 #east face
                    coords.append([yy,xx,1])
                    #cellid.append([nx*ny])
                else:
                    mat_id[yy,xx-1] = idn
                    faces[yy,xx-1] = 1 #west face
                    coords.append([yy,xx-1,1])
                    #cellid.append([xx*yy])
            if mat_id[yy,xx] == 0 and mat_id[yy,xx-1] == 1: # inactive cells to right
                mat_id[yy,xx] = idn
                faces[yy,xx] = 2 #east face
                coords.append([yy,xx,1])
                #cellid.append([xx*yy]) 
    coords = np.asarray(coords)
    cellid = np.asarray(cellid)
    return mat_id, faces, coords 

def find_cells(mat1d,eq,val):
    '''
    finds cell IDs of  specific val
    mat1d: list of material IDs (reshaped matrix)
    eq: <string> "equal" or "not" --> determines whether to search for values equal to val or not equal to val
    returns: np array of indices of cells with val
    '''
    if eq is "equal":
        cells = []
        for i in range(0,np.shape(mat1d)[0]):
            if mat1d[i] == val:
                cells.append(i)
        cells = np.asarray(cells)
        
    else:
        cells = []
        for i in range(0,np.shape(mat1d)[0]):
            if mat1d[i] != val:
                cells.append(i)
        cells = np.asarray(cells)
    return cells  
