# %% 
import os 
import pandas as pd
import warnings
warnings.filterwarnings('ignore')
'''
04.25.2025
Christian Dewey 
for meanders ms

import bc concentrations and interpolate
'''




def load_bc_data(year: str):
    print('>>> loading chem bc data')

    ## load bc data into dictionary 

    mws = {'aluminum':26.982, 
           'calcium': 40.078,
           'chloride': 35.453,
           'iron': 55.845, 
           'dic': 12.011,
           'potassium':39.098,
           'magnesium': 24.305, 
           'sodium': 22.990,
           'nitrate': 62.0049,
           'silicon': 62.0049, 
           'sulfate': 96.06,
           'npoc': 12.011}

    bc_data = {}
    csv_list = [f for f in os.listdir('../bc_chem_data') if '.csv' in f]
    
    for f in csv_list:
        print("\n"+f)
        #try:
        data = pd.read_csv('../bc_chem_data/'+f)

        component = f.split('.')[0].split('_')[-1]

        print('  ' + component + ' loaded')

        df = data[1:].copy()

        df['date'] = pd.to_datetime(df['date'])

        df[component] = df[component].astype('float')
        
        unit = data.iloc[0,1]
        
        temp_date = df['date']

        temp_conc = df[component]

        interpolated_conc = []

        if unit == 'ppm':
            conversion = 1000 * mws[component]
        elif unit == 'ppb':
            conversion = 1e6 * mws[component]
        elif unit == 'mg.L-1':
            conversion = 1000 * mws[component]
        elif unit == 'uM':
            conversion = 1e6
        elif unit == 'pH':
            conversion = 1

        for i in range(1,len(temp_date)-1):

            t_i =[temp_date[i], temp_conc[i]/ conversion]
            
            interpolated_conc.append(t_i)

            diff_hr = (temp_date[i+1]-temp_date[i]).total_seconds()/3600
            
            if diff_hr > 24.0:

                days_btwn = diff_hr / 24

                delta_conc = (temp_conc[i+1] - temp_conc[i]) / days_btwn

                conc_n = temp_conc[i]

                for d in range(1,int(days_btwn)):

                    conc_n = conc_n + delta_conc

                    t_j = [temp_date[i] + pd.Timedelta(hours=d * 24, minutes=0, seconds=0), (conc_n + delta_conc) / conversion ]

                    interpolated_conc.append(t_j)

        df_c = pd.DataFrame(interpolated_conc, columns=['date',component+'_M'])

        bc_data[component] = df_c

        '''except:
            print(Exception)
            print(component + ' not loaded')'''

    bc = {}  

    for component in bc_data:

        temp = bc_data[component]

        if year == '2018':
            time_window = temp[(temp['date']>=pd.Timestamp(2018,4,1)) & (temp['date']<=pd.Timestamp(2018,10,31))]

        elif year == '2019':
            time_window = temp[(temp['date']>=pd.Timestamp(2019,4,19)) & (temp['date']<=pd.Timestamp(2019,10,2))]

        bc[component] = time_window
   
    pd.options.mode.chained_assignment = None

    for i in range(len(bc['nitrate']['nitrate_M'])-1):

        if (bc['nitrate']['nitrate_M'].iloc[i] <= 0.0) :

            prev = bc['nitrate']['nitrate_M'].iloc[i-1].copy()

            bc['nitrate']['nitrate_M'].iloc[i] = prev

    return bc




def write_river_trans_chem_blocks(year: str):    

    """
    writes RIVER transport and chemistry boundaries
    uses data at 24 h frequency
    """

    print('>>> writing river transport chem blocks')

    # check if files exists, if they do, remove them
    files_to_write = ['river_transport_constraint.txt','river_chem.txt']

    for f in files_to_write:

        if os.path.exists(f):

            os.remove(f)


    # start with chemistry 
    with open('TEMPLATE-constraint.txt','r') as file:

        f = file.readlines()
    
    bc = load_bc_data(year)

    if year == '2018':
        diff_d = (pd.Timestamp(2018,11,1)-pd.Timestamp(2018,4,1)).total_seconds()/3600/24

    elif year == '2019':
        diff_d = (pd.Timestamp(2019,10,2)-pd.Timestamp(2019,4,19)).total_seconds()/3600/24

    for d in range(int(diff_d)-1):

        f[0] = '\nCONSTRAINT  from_river_conc_'+str(d*24)+'\n'
        f[2] = '    H+          %.2f  Z\n' %(bc['pH'].iloc[d,1])
        f[5] = '    Al+++       %.2e  T\n' %(bc['aluminum'].iloc[d,1]) #######
        f[6] = '    Ca++        %.2e  T\n' %(bc['calcium'].iloc[d,1])
        f[7] = '    Cl-         %.2e  T\n' %(bc['chloride'].iloc[d,1])
        f[12] = '    K+          %.2e  T\n' %(bc['potassium'].iloc[d,1])
        f[13] = '    Mg++        %.2e  T\n' %(bc['magnesium'].iloc[d,1]) #######
        f[15] = '    Na+         %.2e  T\n' %(bc['sodium'].iloc[d,1])
        f[16] = '    NO3-        %.2e  T\n' %(bc['nitrate'].iloc[d,1])
        f[18] = '    SiO2(aq)    %.2e  T\n' %(bc['silicon'].iloc[d,1])
        f[19] = '    SO4--       %.2e  T\n' %(bc['sulfate'].iloc[d,1])
        f[20] = '    SOC(aq)     %.2e  T\n' %(bc['npoc'].iloc[d,1])
        f[21] = '    Tracer      %.2e  T\n' %(1e-6)

        with open('river_chem.txt','a') as file:
            file.writelines(f)
   
    with open('river_chem.txt','r') as file:
        river_chem_blocks = file.readlines()


    # now transport 
    start_string = '\nTRANSPORT_CONDITION  from_river\n    TIME_UNITS h\n    TYPE dirichlet_zero_gradient\n     CONSTRAINT_LIST\n' 

    with open('river_transport_constraint.txt','a') as file:
        file.writelines(start_string)

    for d in range(int(diff_d)-1):
            
        f[3] = '      %s.d0  from_river_conc_%s\n' %(d*24,d*24)

        with open('river_transport_constraint.txt','a') as file:

            file.writelines(f[3])

    fline = '    /\nEND\n'

    with open('river_transport_constraint.txt','a') as file:
        file.writelines(fline)

    with open('river_transport_constraint.txt','r') as file:
        river_transport_constraint = file.readlines()

    # constraints are written to .txt, but also returned here for use in other fncs 
    return river_chem_blocks, river_transport_constraint




def write_top_trans_chem_blocks(year: str):    
    """
    writes TOP transport and chemistry boundaries
    uses data at 24 h frequency
    chemistry constraints are same as river
    within the input file, there is also a constant dirichlet flux representing rain 
    """

    print('>>> writing top transport chem blocks')

    # check if files exists, if they do, remove them
    files_to_write = ['top_transport_constraint.txt','top_chem.txt']

    for f in files_to_write:

        if os.path.exists(f):

            os.remove(f)


    # start with chemistry 
    with open('TEMPLATE-constraint.txt','r') as file:

        f = file.readlines()
    
    bc = load_bc_data(year = year)

    if year == '2018':
        diff_d = (pd.Timestamp(2018,11,1)-pd.Timestamp(2018,4,1)).total_seconds()/3600/24

    elif year == '2019':
        diff_d = (pd.Timestamp(2019,10,2)-pd.Timestamp(2019,4,19)).total_seconds()/3600/24

    for d in range(int(diff_d)-1):

        f[0] = '\nCONSTRAINT  from_top_conc_'+str(d*24)+'\n'
        f[2] = '    H+          %.2f  Z\n' %(bc['pH'].iloc[d,1])
        f[5] = '    Al+++       %.2e  T\n' %(bc['aluminum'].iloc[d,1]) #######
        f[6] = '    Ca++        %.2e  T\n' %(bc['calcium'].iloc[d,1])
        f[7] = '    Cl-         %.2e  T\n' %(bc['chloride'].iloc[d,1])
        f[12] = '    K+          %.2e  T\n' %(bc['potassium'].iloc[d,1])
        f[13] = '    Mg++        %.2e  T\n' %(bc['magnesium'].iloc[d,1]) #######
        f[15] = '    Na+         %.2e  T\n' %(bc['sodium'].iloc[d,1])
        f[16] = '    NO3-        %.2e  T\n' %(bc['nitrate'].iloc[d,1])
        f[18] = '    SiO2(aq)    %.2e  T\n' %(bc['silicon'].iloc[d,1])
        f[19] = '    SO4--       %.2e  T\n' %(bc['sulfate'].iloc[d,1])
        f[20] = '    SOC(aq)     %.2e  T\n' %(bc['npoc'].iloc[d,1])
        f[21] = '    Tracer      %.2e  T\n' %(1e-6)

        with open('top_chem.txt','a') as file:
            file.writelines(f)
   
    with open('top_chem.txt','r') as file:
        top_chem_blocks = file.readlines()


    # now transport 
    start_string = '\nTRANSPORT_CONDITION  from_top\n    TIME_UNITS h\n    TYPE zero_gradient\n     CONSTRAINT_LIST\n' 

    with open('top_transport_constraint.txt','a') as file:

        file.writelines(start_string)

    for d in range(int(diff_d)-1):
            
        f[3] = '      %s.d0  from_top_conc_%s\n' %(d*24,d*24)
        
        with open('top_transport_constraint.txt','a') as file:

            file.writelines(f[3])

    fline = '    /\nEND '

    with open('top_transport_constraint.txt','a') as file:
        file.writelines(fline)

    with open('top_transport_constraint.txt','r') as file:
        top_transport_constraint = file.readlines()

    return top_chem_blocks, top_transport_constraint




def write_regions(nx:int):
    print('>>> writing regions')

    region_text = ""

    for ix in range(0,nx):

        region_text = region_text + f"\nREGION top_bc_reg_{ix}\n  FILE xxgrid010-mz-cxc-top.h5\n/"

    return region_text




def generate_transient_flow_conditions(nx: int, upstream_file: str, downstream_file:str):  
    print('>>> generating transient flow conditions')
    upstream_ref = pd.read_csv(upstream_file, sep='\t',header=2,index_col=False)
    
    downstream_ref = pd.read_csv(downstream_file, sep='\t',header=2,index_col=False)
    
    #print(upstream_file, downstream_file)
    #print(upstream_ref)
    #print(downstream_ref)

    start_line = ['TIME_UNITS h\nDATA_UNITS m\n!h  x   y   z\n']

    os.makedirs('trans-top-bcs', exist_ok=True)

    for dx in range(0,nx):

        fname = f'trans-top-bcs/top_hydro_bc_at_{dx}.txt'

        if os.path.exists(fname):
            os.remove(fname)

        with open(fname, 'a') as file:
            file.writelines(start_line)

        newlines = []

        for i in range(len(downstream_ref['!h'])):

            up = upstream_ref['z'].iloc[i] 

            down = downstream_ref['z'].iloc[i]

            dh = (up-down) / nx

            hx = up - (dh * dx) 

            newlines.append(f'{i:.4E}\t{0:.4E}\t{0:.4E}\t{hx:.4E}\n')

        with open(fname, 'a') as file:
            file.writelines(newlines)
            
            


def write_transient_flow_conditions_block(nx:int, upstream_h:float, downstream_h:float, us_file:str, ds_file:str): 
    print('>>> writing flow conditions block')

    generate_transient_flow_conditions(nx = nx,
                                    upstream_file = us_file,
                                    downstream_file = ds_file)

    flow_conditions_text = ""

    dh = (upstream_h - downstream_h) / nx 

    hx = upstream_h

    for ix in range(0,nx):

        hx = hx -dh 

        flow_conditions_text = flow_conditions_text + f"\nFLOW_CONDITION top_bc_{ix}\n  TYPE\n    LIQUID_PRESSURE seepage\n  /\n  CYCLIC\n  DATUM FILE trans-top-bcs/top_hydro_bc_at_{ix}.txt\n  LIQUID_PRESSURE 101325.d0\n/"

    return flow_conditions_text



def write_static_flow_conditions_block(nx:int, upstream_h:float, downstream_h:float):

    flow_conditions_text = ""

    dh = (upstream_h - downstream_h) / nx 

    hx = upstream_h

    for ix in range(0,nx):

        hx = hx -dh 
        
        flow_conditions_text = flow_conditions_text + f"\nFLOW_CONDITION top_bc_{ix}\n  TYPE\n    LIQUID_PRESSURE seepage\n  /\n  CYCLIC\n  DATUM 0.d0 0.d0 {hx:.3f}d0\n  LIQUID_PRESSURE 101325.d0\n/"
        
    return flow_conditions_text


def write_bc_blocks(nx: int):
    print('>>> writing bc blocks')

    bc_text = ""

    for ix in range(0,nx):

        bc_text = bc_text + f'\nBOUNDARY_CONDITION top_{ix}\n  FLOW_CONDITION top_bc_{ix}\n  TRANSPORT_CONDITION from_top\n  REGION top_bc_reg_{ix}\n/'

    return bc_text




def assemble_transient_pflotran_input(fname: str, 
                            year: str,
                            us_file: str,
                            ds_file: str,
                            up_h_i: float = 1.94,
                            down_h_i: float = 1.66,
                            nx: int = 108):


    region_block = write_regions(nx = nx)

    flow_conditions_block = write_transient_flow_conditions_block(nx = nx, 
                                                  upstream_h = up_h_i,
                                                  downstream_h = down_h_i,
                                                  us_file = us_file,
                                                  ds_file = ds_file)

    bc_block = write_bc_blocks(nx = nx)  

    river_chem_blocks, river_trans_block = write_river_trans_chem_blocks(year)

    top_chem_blocks, top_trans_block = write_top_trans_chem_blocks(year)


    ## read in static chunks
    with open('TEMPLATE-pflotran.in','r') as file:
            template_file = file.readlines()

    chunks = []
    chunk_n = []

    for l in template_file:
        
        if "$%$%$% CHUNK DELIM %^%^%^" in l:
            
            chunks.append(chunk_n)
            chunk_n = []
            
        else:
            
            chunk_n.append(l)

    if os.path.exists(fname):
        os.remove(fname)
    
    with open(fname,'a') as file:
        file.writelines(chunks[0])
        file.writelines(region_block)
        file.writelines(chunks[1])
        file.writelines(flow_conditions_block)
        file.writelines(chunks[2])
        file.writelines(river_chem_blocks)   
        file.writelines(top_chem_blocks)    
        file.writelines(chunks[3])
        file.writelines(river_trans_block)
        file.writelines(top_trans_block)
        file.writelines(chunks[4])
        file.writelines(['\n\n'])
        file.writelines(bc_block)
        file.writelines(chunks[5])


def assemble_static_pflotran_input(fname: str, 
                            year: str,
                            up_h_i: float = 1.94,
                            down_h_i: float = 1.66,
                            nx: int = 108):


    region_block = write_regions(nx = nx)

    flow_conditions_block = write_static_flow_conditions_block(nx = nx, 
                                                  upstream_h = up_h_i,
                                                  downstream_h = down_h_i)

    bc_block = write_bc_blocks(nx = nx)  


    ## read in static chunks
    with open('TEMPLATE-pflotran-spin.in','r') as file:
            template_file = file.readlines()

    chunks = []
    chunk_n = []

    for l in template_file:
        
        if "$%$%$% CHUNK DELIM %^%^%^" in l:
            
            chunks.append(chunk_n)
            chunk_n = []
            
        else:
            
            chunk_n.append(l)

    if os.path.exists(fname):
        os.remove(fname)
    
    with open(fname,'a') as file:
        file.writelines(chunks[0])
        file.writelines(region_block)
        file.writelines(chunks[1])
        file.writelines(flow_conditions_block)
        file.writelines(chunks[2])
        file.writelines(bc_block)
        file.writelines(chunks[3])


if __name__ == '__main__':
        
    fname = 'pflotran-mzt19.in'

    assemble_transient_pflotran_input(fname, 
                            year = '2019',
                            us_file = "hydro_us_2019_4-21_10-2-MZT.txt",
                            ds_file = "hydro_ds_2019_4-21_10-2-MZT.txt",
                            up_h_i = 1.94,
                            down_h_i= 1.66,
                            nx = 108)
    
    print(f'\n{fname} written to {os.getcwd()}\n')

    fname = 'pflotran-spin-mzt19.in'

    assemble_static_pflotran_input(fname, 
                            year = '2019',
                            up_h_i = 1.94,
                            down_h_i= 1.66,
                            nx = 108)
    
    print(f'\n{fname} written to {os.getcwd()}\n')

