import os 
import h5py 
import numpy as np
import matplotlib as mpl
import matplotlib.pyplot as plt
#from google.cloud import storage
## christian dewey
''' 
    

'''
def get_locs_year(data_dir):
    if 'mzt' in str.split(data_dir,'/')[-2]:
        distances = [1.0, 16, 27, 40, 50] #m 
        depths = [2.0,2.0,2.0,2.0,2.0]

    else:
        distances = [0.5, 16, 31, 46, 60.]
        depths = [1.7,2.0,2.1,2.4,2.5]

    locs = [(i,d) for i, d in zip(distances,depths)]


    if '18' in str.split(data_dir,'/')[-2]:
        year = 2018
    elif '19' in str.split(data_dir,'/')[-2]:
        year = 2019

    return locs, year

def load_from_gcs(gcs_obj_path, project = "dewey-etal-meanders", bucket = "dewey-etal-meanders" ):

    tempdir = "./.temp/" + gcs_obj_path

    if os.path.exists(tempdir):
        print(f"{gcs_obj_path} already loaded")
    else:
        print(f"...loading {gcs_obj_path}")
        storage_client = storage.Client(project)
        bucket = storage_client.bucket(bucket)
        blob = bucket.blob(gcs_obj_path)
        
        directory = os.path.dirname(tempdir)
        if not os.path.exists(directory):
            os.makedirs(directory)
        blob.download_to_filename(tempdir)

def extractComponentList(h5):
    file = h5py.File(h5,'r')
    groups = list(file.keys())	

    componentList = []
    for gg in groups:
        if 'Time' in gg:
            componentList = list(file[gg].keys())	

    return componentList


def extractTimes(h5):
    file = h5py.File(h5,'r')
    groups = list(file.keys())	

    times = []
    for gg in groups:
        if 'Time' in gg: times.append(float(gg[7:18])) # gets time step 

    times = np.array([times]).T

    return times

def extractComponent_transect(h5,component,return_times,rm_bc_cells):
    file = h5py.File(h5,'r')
    groups = list(file.keys())	
    dx, dy = 1, 1
    nx, ny = int(1/dx), int(1/dy) 

    componentList = []
    times = []
    data = []
    for gg in groups:
        if 'Time' in gg:
            times.append(float(gg[7:18])) # gets time step 
            dset = np.array(file[gg][component])
            if rm_bc_cells == 'y': component_transect = dset[nx,ny,1:-1] # returns an array containing value of component at all cells along model transect at given time
            else: component_transect = dset[nx-1,ny-1,:]  #			else: component_transect = dset[nx,ny,:]

            componentList.append(component_transect)

    componentList = np.asarray(componentList)

    #print(componentList)
    #print(times)
    times = np.array([times]).T
    data = np.append(times,componentList,axis = 1)
    data = data[data[:,0].argsort()]
    times = data[:,0]
    data = data[:,1:]
    
    if return_times == 'y': return times, data
    else: return data 

def extractComponent_atTime(h5,component,dz,dist,time):
    file = h5py.File(h5,'r')
    groups = list(file.keys())	
    dx, dy = 1, 1
    nx, ny, nz = int(1/dx), int(1/dy), int(dist/dz) 

    componentList = []
    data = []
    
    for gg in groups:
        if str(np.format_float_scientific(time,precision=5,unique=False)).replace('e','E') in gg:
            dset = np.array(file[gg][component])
            componentAtCoords = dset[nx,ny,nz]
    return componentAtCoords


def extractTransect_atTime(h5,component,time,discretization_dir = 'z',rm_bc_cells=False):
    file = h5py.File(h5,'r')
    groups = list(file.keys())	
    componentList = []

    if discretization_dir == 'z':
        dx, dy = 1, 1
        nx, ny = int(1/dx), int(1/dy) 
        for gg in groups:
            if str(np.format_float_scientific(time,precision=5,unique=False)).replace('e','E') in gg:
                dset = np.array(file[gg][component])
                if rm_bc_cells: component_transect = dset[nx-1,ny-1,1:-1] # returns an array containing value of component at all cells along model transect at given time
                else: component_transect = dset[nx-1,ny-1,:]  #			else: component_transect = dset[nx,ny,:]
                componentList.append(component_transect)

    elif discretization_dir == 'x':
        dz, dy = 1, 1
        nz, ny = int(1/dz), int(1/dy) 
        for gg in groups:
            if str(np.format_float_scientific(time,precision=5,unique=False)).replace('e','E') in gg:
                dset = np.array(file[gg][component])
                if rm_bc_cells: component_transect = dset[1:-1,ny-1,nz-1] # returns an array containing value of component at all cells along model transect at given time
                else: component_transect = dset[:,ny-1,nz-1]  #			else: component_transect = dset[nx,ny,:]
                componentList.append(component_transect)

    elif discretization_dir == 'y':
        dz, dx = 1, 1
        nz, nx = int(1/dz), int(1/dx) 
        for gg in groups:
            if str(np.format_float_scientific(time,precision=5,unique=False)).replace('e','E') in gg:
                dset = np.array(file[gg][component])
                if rm_bc_cells: component_transect = dset[nx-1,1:-1,nz-1] # returns an array containing value of component at all cells along model transect at given time
                else: component_transect = dset[nx-1,:,nz-1]  #			else: component_transect = dset[nx,ny,:]
                componentList.append(component_transect)

    componentList = np.asarray(componentList)
    return componentList


def plot_profile(results,component, time, d, xyz, ax, unit = None, flip = False, logscale = False):
    # length is determined from component_data dims
    component_data = results[component][time]
    component_data = component_data.flatten()
    if logscale:
        component_data[component_data < 0] = np.log10(np.abs(component_data[component_data <0])) 
        component_data[component_data == 0] = 0
        #component_data[component_data > 0] = np.log10(component_data[component_data >0])



    #length = np.shape(component_data)[1] * d

    length = len(component_data) * d


    if ax == None:
        _, ax = plt.subplots()

    
    if unit == 'uM':
        factor = 1e6
    elif unit == 'mM':
        factor = 1e3
    else:
        factor = 1 	
    
    
    if xyz == 'z':
        y = np.atleast_2d(np.arange(0,length,d))
        x = np.atleast_2d(component_data)
        ax.scatter([xp*factor for xp in x],y, label=component)
        if flip:
            ax.set_ylim(0, length)
        if unit == 'rate':
            if logscale:
                ax.set_xlabel('Log10(Rate [mol_m^3-sec])')
            else:
                ax.set_xlabel('Rate [mol_m^3-sec]')
        elif unit == 'pH':
            ax.set_xlabel('pH')
        else:
            ax.set_xlabel('Concentration [%s]' %(unit))
            
        ax.set_ylabel('Distance [m]')
    else:
        x = np.atleast_2d(np.arange(0,length,d))
        y = np.atleast_2d(component_data)
        ax.scatter(x,[yp*factor for yp in y], label=component)
        if unit == 'rate':
            ax.set_ylabel('Rate [mol_m^3-sec]')
        elif unit == 'pH':
            ax.set_ylabel('pH')
        else:
            ax.set_ylabel('TConcentration [%s]' %(unit))
        ax.set_xlabel('Distance [m]')
    return ax



def plot_time_series_h5(component_data, distance, discretization,unit=None, ax =None, startdate = None, meander = 'MZ',reverse = False):

    cmap = mpl.cm.get_cmap('viridis')
    # extract all colors from the .jet map
    cmaplist = [cmap(i) for i in np.arange(0,1,0.2)]

    if meander == 'MZ':
        loc_dist = { 1: '1',16 :'2',27:'3',40:'4',50:'5' }
    elif meander == 'MC':
        loc_dist = { 0.5: '1',16 :'2',31:'3',46:'4',61.5:'5' }	
    loc_colors = {'river': 'mediumblue', '1': cmaplist[0],'2':cmaplist[1],'3':cmaplist[2],'4':cmaplist[3],'5':cmaplist[4] }

    loc_symbols = {'river':'s', '1': 'o', '2': 'p','3': 'd','4': 'P', '5':'X' }


    if ax == None:
        _, ax = plt.subplots()
    
    times = component_data.keys()
    
    if unit == 'uM':
        factor = 1e6
    elif unit == 'mM':
        factor = 1e3
    else:
        factor = 1 
    
    y = []
    i = int(distance/discretization)-1
    times = list(times)
    times.sort()

    for t in times:
        ct = component_data[t][0][i]
        if reverse is True:
            y.append(ct*-1)
        else:
            y.append(ct)

    if startdate:
        times = [np.timedelta64(int(t),'h') for t in times]
        datex = [(startdate + dt) for dt in times]
        timesx = datex 
        ax.plot(timesx,[yp*factor for yp in y], color = loc_colors[loc_dist[distance]])
        ax.set_xlabel('Date')
    else:
        timesx = times
        ax.plot(timesx,[yp*factor for yp in y], color = loc_colors[loc_dist[distance]])
        ax.set_xlabel('Time [h]')

    if unit != 'pH':
        ax.set_ylabel('Concentration [%s]' %(unit))
    elif unit == 'pH':
        ax.set_ylabel('pH')
    

    return ax



def plot_time_series(component_data, times, distance, discretization,unit=None, ax =None, startdate = None, meander = 'MZ',reverse = False):

    cmap = mpl.cm.get_cmap('viridis')
    # extract all colors from the .jet map
    cmaplist = [cmap(i) for i in np.arange(0,1,0.2)]

    if meander == 'MZ':
        loc_dist = { 1: '1',16 :'2',27:'3',40:'4',50:'5' }
    elif meander == 'MC':
        loc_dist = { 0.5: '1',16 :'2',31:'3',46:'4',60.0:'5' }	
    loc_colors = {'river': 'mediumblue', '1': cmaplist[0],'2':cmaplist[1],'3':cmaplist[2],'4':cmaplist[3],'5':cmaplist[4] }


    if ax == None:
        _, ax = plt.subplots()
    
    if unit == 'uM':
        factor = 1e6
    elif unit == 'mM':
        factor = 1e3
    else:
        factor = 1 
    
    y = []
    times = [int(t) for t in times]
    times.sort()

    for t in range(len(times)):
        ct = component_data[t]
        if reverse is True:
            y.append(ct*-1)
        else:
            y.append(ct)

    if startdate:
        times = [np.timedelta64(int(t),'h') for t in times]
        datex = [(startdate + dt) for dt in times]
        timesx = datex 
        ax.plot(timesx,[yp*factor for yp in y], color = loc_colors[loc_dist[distance]])
        ax.set_xlabel('Date')
    else:
        timesx = times
        ax.plot(timesx,[yp*factor for yp in y], color = loc_colors[loc_dist[distance]])
        ax.set_xlabel('Time [h]')

    if unit != 'pH':
        ax.set_ylabel('Concentration [%s]' %(unit))
    elif unit == 'pH':
        ax.set_ylabel('pH')
    

    return ax


def plot_pressure_time_series(component_data, distance, discretization,unit=None, ax =None, startdate = None):
    if ax == None:
        _, ax = plt.subplots()
    
    times = component_data.keys()
    
    if unit == 'mPa':
        factor = 1e3
    elif unit == 'mASL':
        factor = (9.81 * 998)
    else:
        factor = 1 
    
    y = []
    i = int(distance/discretization)-1
    times = list(times)
    times.sort()


    cmap = mpl.cm.get_cmap('viridis')
    # extract all colors from the .jet map
    cmaplist = [cmap(i) for i in np.arange(0,1,0.2)]

    loc_dist = { 2.0: '1',16 :'2',27:'3',40:'4',50:'5' }
    loc_colors = {'river': 'mediumblue', '1': cmaplist[0],'2':cmaplist[1],'3':cmaplist[2],'4':cmaplist[3],'5':cmaplist[4] }

    for t in times:
        ct = component_data[t][0][i]
        y.append( ct-101325)

    if startdate:
        times = [np.timedelta64(int(t),'h') for t in times]
        datex = [(startdate + dt) for dt in times]
        timesx = datex 
        if unit == 'mASL':
            ax.plot(timesx,[(yp/factor)+2717.5 for yp in y], alpha=1.0, linestyle= '--',linewidth = 0.75,color = loc_colors[loc_dist[distance]] )
            ax.set_ylabel('Elevation [%s]' %(unit))

        else:
            ax.plot(timesx,[yp/factor for yp in y], alpha=1.0,linestyle= '--',linewidth = 0.75)
            ax.set_ylabel('Pressure [%s]' %(unit))

        ax.set_xlabel('Date')
    else:
        timesx = times
        ax.plot(timesx,[yp/factor for yp in y],linestyle= '--',)
        ax.set_xlabel('Time [h]')
        ax.set_ylabel('Pressure [%s]' %(unit))
    

    return ax

def plot_gwObs_v_time(df, location, ax = None, color = None):
    if ax == None:
        _, ax = plt.subplots()
    
    times = df['Date and time']
    if color:
        ax.scatter(times,df[location], color = color,  marker = 'x', s = 1 , alpha=0.5)
    else:
        ax.scatter(times,df[location],  marker = 'x', s = 1 , alpha=0.5)
    
    ax.set_xlabel('Date')

    ax.set_ylabel('Elevation (mASL)')

    return ax


def plot_chemObs_v_time(df, location, ax = None, color = None):
    if ax == None:
        _, ax = plt.subplots()
    
    times = df['Date and time']
    if color:
        ax.scatter(times,df[location], color = color,  marker = 'x', s = 1 )
    else:
        ax.scatter(times,df[location],  marker = 'x', s = 1 )
    
    ax.set_xlabel('Date')

    ax.set_ylabel('Elevation [mASL]')

    return ax