# %%
import os
import pandas as pd
from pathlib import Path

# Get the directory containing this script for relative path resolution
SCRIPT_DIR = Path(__file__).parent.resolve()
BUILD_DIR = SCRIPT_DIR.parent  # pflotran/build directory

'''
import bc concentrations and interpolate

'''

def load_bc_data(year: str, data_dir: str):
    
    ## load bc data into dictionary 

    mws = {'aluminum':26.982, 
        'iron': 55.845, 
        'sodium': 22.990,
            'npoc': 12.011,
            'potassium':39.098,
            'chloride': 35.453,
            'calcium': 40.078,
            'sulfate': 96.06,
            'nitrate': 62.0049,
            'magnesium': 24.305, 
            'ammonia': 17.031 ,
            'dic': 12.011}

    bc_data = {}

    for f in os.listdir(data_dir):

        try:
            data = pd.read_csv(data_dir + f)

            component = f.split('.')[0].split('_')[-1]

            print(component + ' loaded')

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

        except (FileNotFoundError, KeyError, ValueError) as e:
            print(f'{component} not loaded: {e}')

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



def write_river_trans_chem_constraints(year: str, input_dir: str, data_dir: str):    
    bc = load_bc_data(year = year, data_dir=data_dir)
    files_to_write = ['river_transport_constraint.txt','river_chem.txt']
    for f in files_to_write:
        if os.path.exists(input_dir + f):
            os.remove(input_dir + f)

    with open(input_dir + 'TEMPLATE-constraint.txt','r') as file:
        f = file.readlines()

    if year == '2018':
        diff_d = (pd.Timestamp(2018,11,1)-pd.Timestamp(2018,4,1)).total_seconds()/3600/24
    elif year == '2019':
        diff_d = (pd.Timestamp(2019,10,2)-pd.Timestamp(2019,4,19)).total_seconds()/3600/24

    for d in range(int(diff_d)-1):
        f[0] = '\nCONSTRAINT  from_river_conc_'+str(d*24)+'\n'
        f[2] = '  H+          %.2f      P\n' %(bc['pH'].iloc[d,1])
        f[4] = '  Cl-         %.2e  T\n' %(bc['chloride'].iloc[d,1])
        f[5] = '  SO4--       %.2e  T\n' %(bc['sulfate'].iloc[d,1])
        f[6] = '  HCO3-       %.2e  T\n' %(bc['dic'].iloc[d,1])
        f[8] = '  Ca++        %.2e  T\n' %(bc['calcium'].iloc[d,1])
        #f[9] = '  Mg++        %.2e  Z\n' %(bc['magnesium'].iloc[d,1])
        f[15] = '  Tracer      %.2e  T\n' %(1e-6)
        f[12] = '  K+          %.2e  T\n' %(bc['potassium'].iloc[d,1])
        f[13] = '  Na+         %.2e  T\n' %(bc['sodium'].iloc[d,1])
        f[17] = '  DOC-        %.2e  T\n' %(bc['npoc'].iloc[d,1])
        f[19] = '  NO3-        %.2e  T\n' %(bc['nitrate'].iloc[d,1])
        #f[22] = '  Tracer1     %.2e  T\n' %(1e-10)

        with open(input_dir + 'river_chem.txt','a') as file:
            file.writelines(f)
   
    with open(input_dir + 'river_chem.txt','r') as file:
        river_chem_blocks = file.readlines()

    start_string = '\nTRANSPORT_CONDITION  from_river\n    TIME_UNITS h\n    TYPE dirichlet_zero_gradient\n     CONSTRAINT_LIST\n' 

    with open(input_dir + 'river_transport_constraint.txt','a') as file:

        file.writelines(start_string)

    for d in range(int(diff_d)-1):
            
        f[3] = '      %s.d0  from_river_conc_%s\n' %(d*24,d*24)
        with open(input_dir + 'river_transport_constraint.txt','a') as file:

            file.writelines(f[3])

    fline = '    /\nEND '

    with open(input_dir + 'river_transport_constraint.txt','a') as file:
        file.writelines(fline)

    with open(input_dir + 'river_transport_constraint.txt','r') as file:
        river_transport_constraint = file.readlines()

    return river_chem_blocks, river_transport_constraint


def write_top_trans_chem_constraints(year: str, input_dir: str, data_dir: str):    
    bc = load_bc_data(year = year, data_dir=data_dir)
    files_to_write = ['top_transport_constraint.txt','top_chem.txt']
    for f in files_to_write:
        if os.path.exists(input_dir + f):
            os.remove(input_dir + f)

    with open(input_dir + 'TEMPLATE-constraint.txt','r') as file:
        f = file.readlines()

    if year == '2018':
        diff_d = (pd.Timestamp(2018,11,1)-pd.Timestamp(2018,4,1)).total_seconds()/3600/24
    elif year == '2019':
        diff_d = (pd.Timestamp(2019,10,2)-pd.Timestamp(2019,4,19)).total_seconds()/3600/24

    for d in range(int(diff_d)-1):
        f[0] = '\nCONSTRAINT  from_top_conc_'+str(d*24)+'\n'
        f[2] = '  H+          %.2f      P\n' %(bc['pH'].iloc[d,1])
        f[4] = '  Cl-         %.2e  T\n' %(bc['chloride'].iloc[d,1])
        f[5] = '  SO4--       %.2e  T\n' %(bc['sulfate'].iloc[d,1])
        f[6] = '  HCO3-       %.2e  T\n' %(bc['dic'].iloc[d,1])
        f[8] = '  Ca++        %.2e  T\n' %(bc['calcium'].iloc[d,1])
        #f[9] = '  Mg++        %.2e  Z\n' %(bc['magnesium'].iloc[d,1])
        f[15] = '  Tracer      %.2e  T\n' %(1e-6)
        f[12] = '  K+          %.2e  T\n' %(bc['potassium'].iloc[d,1])
        f[13] = '  Na+         %.2e  T\n' %(bc['sodium'].iloc[d,1])
        f[17] = '  DOC-        %.2e  T\n' %(bc['npoc'].iloc[d,1])
        f[19] = '  NO3-        %.2e  T\n' %(bc['nitrate'].iloc[d,1])
        #f[22] = '  Tracer1     %.2e  T\n' %(1e-6)

        with open(input_dir + 'top_chem.txt','a') as file:
            file.writelines(f)
   
    with open(input_dir + 'top_chem.txt','r') as file:
        top_chem_blocks = file.readlines()

    start_string = '\nTRANSPORT_CONDITION  from_top\n    TIME_UNITS h\n    TYPE zero_gradient\n     CONSTRAINT_LIST\n' 

    with open(input_dir + 'top_transport_constraint.txt','a') as file:

        file.writelines(start_string)

    for d in range(int(diff_d)-1):
            
        f[3] = '      %s.d0  from_top_conc_%s\n' %(d*24,d*24)
        with open(input_dir + 'top_transport_constraint.txt','a') as file:

            file.writelines(f[3])

    fline = '    /\nEND '

    with open(input_dir + 'top_transport_constraint.txt','a') as file:
        file.writelines(fline)

    with open(input_dir + 'top_transport_constraint.txt','r') as file:
        top_transport_constraint = file.readlines()

    return top_chem_blocks, top_transport_constraint


def write_regions(nx:int):

    region_text = ""

    for ix in range(0,nx):

        region_text = region_text + f"\nREGION top_bc_reg_{ix}\n  FILE xxgrid010-top.h5\n/"

    return region_text


def write_transient_flow_conditions(nx: int, upstream_file: str, downstream_file:str, input_dir:str):

    upstream_ref = pd.read_csv(upstream_file, sep='\t',header=2,index_col=False)
    
    downstream_ref = pd.read_csv(downstream_file, sep='\t',header=2,index_col=False)

    start_line = ['TIME_UNITS h\nDATA_UNITS m\n!h  x   y   z\n']

    for dx in range(0,nx):

        fname = f'top_hydro_bc_at_{dx}.txt'

        if os.path.exists(input_dir + fname):
            os.remove(input_dir + fname)

        with open(input_dir + fname, 'a') as file:

            file.writelines(start_line)

        newlines = []

        for i in range(len(downstream_ref['!h'])):

            up = upstream_ref['z'].iloc[i] 
            down = downstream_ref['z'].iloc[i]

            dh = (up-down) / nx
            hx = up - (dh * dx) 
            newlines.append(f'{i:.4E}\t{0:.4E}\t{0:.4E}\t{hx:.4E}\n')


        with open(input_dir + fname, 'a') as file:

            file.writelines(newlines)


def write_flow_conditions(nx:int, upstream_h:float, downstream_h:float, spin:bool):

    flow_conditions_text = ""

    dh = (upstream_h - downstream_h) / nx 

    hx = upstream_h

    for ix in range(0,nx):

        hx = hx -dh 
        
        if spin:

            flow_conditions_text = flow_conditions_text + f"\nFLOW_CONDITION top_bc_{ix}\n  TYPE\n    LIQUID_PRESSURE seepage\n  /\n  CYCLIC\n  DATUM 0.d0 0.d0 {hx}d0\n  LIQUID_PRESSURE 101325.d0\n/"
        
        else:

            flow_conditions_text = flow_conditions_text + f"\nFLOW_CONDITION top_bc_{ix}\n  TYPE\n    LIQUID_PRESSURE seepage\n  /\n  CYCLIC\n  DATUM FILE trans-top-bcs/top_hydro_bc_at_{ix}.txt\n  LIQUID_PRESSURE 101325.d0\n/"


    return flow_conditions_text


def write_bc_blocks(nx: int):

    bc_text = ""

    for ix in range(0,nx):

        bc_text = bc_text + f'\nBOUNDARY_CONDITION top_{ix}\n  FLOW_CONDITION top_bc_{ix}\n  TRANSPORT_CONDITION from_river\n  REGION top_bc_reg_{ix}\n/'

    return bc_text


def assemble_pflotran_input(input_dir: str, save_dir: str, data_dir: str, fname: str, year: str, write_trans_flow: bool):
    
    if write_trans_flow:
        
        usfile = '/Users/christiandewey/Code/meander-models/pflotran-files/2D/bcs/mc_up_2019_3993h.txt'
        dsfile = '/Users/christiandewey/Code/meander-models/pflotran-files/2D/bcs/mc_dn_2019_3993h.txt'

        write_transient_flow_conditions(nx=122,upstream_file = usfile ,downstream_file=dsfile,input_dir=input_dir)
         
    region_block = write_regions(nx=122)

    flow_conditions_block = write_flow_conditions(nx=122, upstream_h=1.94, downstream_h=0.89, spin=False)

    bc_block = write_bc_blocks(nx=122)  

    river_chem_blocks, river_trans_block = write_river_trans_chem_constraints(year = year, input_dir = input_dir, data_dir= data_dir)

    top_chem_blocks, top_trans_block = write_top_trans_chem_constraints(year = year, input_dir = input_dir, data_dir= data_dir)

    with open(input_dir + 'pflotran-sim-TEMP-chunk1.in','r') as file:
        chunk1 = file.readlines()

    with open(input_dir + 'pflotran-sim-TEMP-chunk2.in','r') as file:
        chunk2 = file.readlines()

    with open(input_dir + 'pflotran-sim-TEMP-chunk3.in','r') as file:
        chunk3 = file.readlines()
    
    with open(input_dir + 'pflotran-sim-TEMP-chunk4.in','r') as file:
        chunk4 = file.readlines()

    with open(input_dir + 'pflotran-sim-TEMP-chunk5.in','r') as file:
        chunk5 = file.readlines()

    with open(input_dir + 'pflotran-sim-TEMP-chunk6.in','r') as file:
        chunk6 = file.readlines()

    if os.path.exists(save_dir + fname):
        os.remove(save_dir + fname)

    with open(save_dir + fname,'a') as file:
        file.writelines(chunk1)
        file.writelines(region_block)
        file.writelines(chunk2)
        file.writelines(flow_conditions_block)
        file.writelines(chunk3)
        file.writelines(river_chem_blocks)   
        file.writelines(top_chem_blocks)    
        file.writelines(chunk4)
        file.writelines(river_trans_block)
        file.writelines(top_trans_block)
        file.writelines(chunk5)
        file.writelines(['\n\n'])
        file.writelines(bc_block)
        file.writelines(chunk6)
        



if __name__ == '__main__':
    # Use relative paths based on script location
    input_dir = str(SCRIPT_DIR / 'mcp-19') + '/'
    save_dir = str(SCRIPT_DIR / 'mcp-19') + '/'
    data_dir = str(SCRIPT_DIR / 'bc_chem_data') + '/'

    fname = 'pflotran-sim-n.in'

    assemble_pflotran_input(input_dir, save_dir, data_dir, fname, '2019', write_trans_flow=True)

    print(f'\n{fname} written to {save_dir}\n')

# %%
