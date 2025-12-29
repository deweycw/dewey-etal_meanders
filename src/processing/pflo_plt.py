from matplotlib.lines import lineStyles 
import numpy as np
import matplotlib as mpl
import matplotlib.dates as mdates
import processing.pflo_process as pr



def plot_waterLevels(results,gw_obs,startdate,ax):
    distances = [2, 27, 50] #m 

    mpl.rcParams['mathtext.default'] = 'rm'
    mpl.rcParams['legend.fontsize'] = 8

    disc = 0.5

    components = ['Liquid_Pressure [Pa]']

    for component in components:
        df1 = results[component]
        for distance in distances:
            ax = pr.plot_pressure_time_series(df1, distance, discretization=disc, ax=ax, unit='mASL',startdate=startdate)
    obs_locs = ['mzt11', 'mzt13', 'mzt15']
    cmap = mpl.cm.get_cmap('viridis')
    
    cmaplist = [cmap(i) for i in np.arange(0,1,0.2)]

    loc_name = { 'mzt11': '1','MZT1-2D' :'2','mzt13':'3','MZT1-4D':'4','mzt15':'5' }
    loc_colors = {'river': 'mediumblue', '1': cmaplist[0],'2':cmaplist[1],'3':cmaplist[2],'4':cmaplist[3],'5':cmaplist[4] }
    for l in obs_locs:
        pr.plot_gwObs_v_time(gw_obs,l,ax = ax,color=loc_colors[loc_name[l]])
    
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%-d-%b"))
    ax.set_xlabel('Date')
    
    return ax


def plot_pH(results,times,distances,startdate,ax,meander,chem_obs=None):
    components = ['pH']
    for component in components:
        for distance in distances:
            df1 = results[distance][component]
            ax = pr.plot_time_series(df1, times,distance, discretization=0.5, ax=ax, unit='pH', startdate=startdate, meander=meander)
    try:
        factor = 1 #e3
        cmap = mpl.cm.get_cmap('viridis')
        cmaplist = [cmap(i) for i in np.arange(0,1,0.2)]

        if meander == 'MZ':
            obs_locs = ['MZT1-1D', 'MZT1-2D', 'MZT1-3D', 'MZT1-4D', 'MZT1-5D']
            loc_name = { 'MZT1-1D': '1','MZT1-2D' :'2','MZT1-3D':'3','MZT1-4D':'4','MZT1-5D':'5' }
        elif meander == 'MC':
            obs_locs = ['MCP1-1D', 'MCP1-2D', 'MCP1-3D', 'MCP1-4D', 'MCP1-5D']
            loc_name = { 'MCP1-1D': '1','MCP1-2D' :'2','MCP1-3D':'3','MCP1-4D':'4','MCP1-5D':'5' }
        else:
            print(meander, ' is not a valid meander name. MC and MZ are only valid meander names.')

        loc_colors = {'river': 'mediumblue', '1': cmaplist[0],'2':cmaplist[1],'3':cmaplist[2],'4':cmaplist[3],'5':cmaplist[4] }

        loc_symbols = {'river':'s', '1': 'o', '2': 'p','3': 'd','4': 'P', '5':'X' }

        for l in obs_locs:
            df = chem_obs[chem_obs['Well'] == l]
            for component in components:
                mask = df[component].isna()
                df = df[~mask]
                ax.plot(df['Date'], df[component]*factor, linestyle = '-.', linewidth = 0.5, color = loc_colors[loc_name[l]], marker = loc_symbols[loc_name[l]])
    except:
        print('No observations loaded -- plotting simulations results only.')
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%-d-%b"))
    ax.set_xlabel('Date')
    return ax


def plot_DIC(results,times,distances,startdate,ax,meander,chem_obs=None):
    components = ['Total_HCO3- [M]']
    for component in components:
        for distance in distances:
            df1 = results[distance][component]
            ax = pr.plot_time_series(df1, times, distance, discretization=0.5, ax=ax, unit='mM', startdate=startdate, meander=meander)
    
    try:
        components = ['TIC']
        factor = 1 #e3
        cmap = mpl.cm.get_cmap('viridis')
        cmaplist = [cmap(i) for i in np.arange(0,1,0.2)]

        if meander == 'MZ':
            obs_locs = ['MZT1-1D', 'MZT1-2D', 'MZT1-3D', 'MZT1-4D', 'MZT1-5D']
            loc_name = { 'MZT1-1D': '1','MZT1-2D' :'2','MZT1-3D':'3','MZT1-4D':'4','MZT1-5D':'5' }
        elif meander == 'MC':
            obs_locs = ['MCP1-1D', 'MCP1-2D', 'MCP1-3D', 'MCP1-4D', 'MCP1-5D']
            loc_name = { 'MCP1-1D': '1','MCP1-2D' :'2','MCP1-3D':'3','MCP1-4D':'4','MCP1-5D':'5' }
        else:
            print(meander, ' is not a valid meander name. MC and MZ are only valid meander names.')        
            
        loc_colors = {'river': 'mediumblue', '1': cmaplist[0],'2':cmaplist[1],'3':cmaplist[2],'4':cmaplist[3],'5':cmaplist[4] }

        loc_symbols = {'river':'s', '1': 'o', '2': 'p','3': 'd','4': 'P', '5':'X' }

        for l in obs_locs:
            df = chem_obs[chem_obs['Well'] == l]
            for component in components:
                mask = df[component].isna()
                df = df[~mask]
                ax.plot(df['Date'], df[component]*factor, linestyle = '-.', linewidth = 0.5, color = loc_colors[loc_name[l]], marker = loc_symbols[loc_name[l]])
    except:
        print('No observations loaded -- plotting simulations results only.')

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%-d-%b"))
    ax.set_xlabel('Date')
    ax.set_ylabel('DIC (mM)')
    return ax


def plot_Ca(results,times,distances,startdate,ax,meander,chem_obs=None):
    components = ['Total_Ca++ [M]']
    for component in components:
        for distance in distances:
            df1 = results[distance][component]
            ax = pr.plot_time_series(df1, times, distance, discretization=0.5, ax=ax, unit='mM', startdate=startdate, meander=meander)
    try:
        components = ['Ca']
        factor = 1e3
        if meander == 'MZ':
            obs_locs = ['MZT1-1D', 'MZT1-2D', 'MZT1-3D', 'MZT1-4D', 'MZT1-5D']
            loc_name = { 'MZT1-1D': '1','MZT1-2D' :'2','MZT1-3D':'3','MZT1-4D':'4','MZT1-5D':'5' }
        elif meander == 'MC':
            obs_locs = ['MCP1-1D', 'MCP1-2D', 'MCP1-3D', 'MCP1-4D', 'MCP1-5D']
            loc_name = { 'MCP1-1D': '1','MCP1-2D' :'2','MCP1-3D':'3','MCP1-4D':'4','MCP1-5D':'5' }
        else:
            print(meander, ' is not a valid meander name. MC and MZ are only valid meander names.')
        cmap = mpl.cm.get_cmap('viridis')
        cmaplist = [cmap(i) for i in np.arange(0,1,0.2)]

        
        loc_colors = {'river': 'mediumblue', '1': cmaplist[0],'2':cmaplist[1],'3':cmaplist[2],'4':cmaplist[3],'5':cmaplist[4] }
        loc_symbols = {'river':'s', '1': 'o', '2': 'p','3': 'd','4': 'P', '5':'X' }

        for l in obs_locs:
            df = chem_obs[chem_obs['Well'] == l]
            for component in components:
                mask = df[component].isna()
                df = df[~mask]
                ax.plot(df['Date'], df[component]*factor, linestyle = '-.', linewidth = 0.5, color = loc_colors[loc_name[l]], marker = loc_symbols[loc_name[l]])
    except:
        print('No observations loaded -- plotting simulations results only.')
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%-d-%b"))
    ax.set_xlabel('Date')
    ax.set_ylabel('Ca (mM)')
    return ax


def plot_sulfate(results,times,distances,startdate,ax,meander,chem_obs=None):
    components = ['Total_SO4-- [M]']
    for component in components:
        for distance in distances:
            df1 = results[distance][component]
            ax = pr.plot_time_series(df1, times, distance, discretization=0.5, ax=ax, unit='uM', startdate=startdate, meander=meander)
    try:
        components = ['SO4']
        factor = 1e3
        cmap = mpl.cm.get_cmap('viridis')
        cmaplist = [cmap(i) for i in np.arange(0,1,0.2)]

        if meander == 'MZ':
            obs_locs = ['MZT1-1D', 'MZT1-2D', 'MZT1-3D', 'MZT1-4D', 'MZT1-5D']
            loc_name = { 'MZT1-1D': '1','MZT1-2D' :'2','MZT1-3D':'3','MZT1-4D':'4','MZT1-5D':'5' }
        elif meander == 'MC':
            obs_locs = ['MCP1-1D', 'MCP1-2D', 'MCP1-3D', 'MCP1-4D', 'MCP1-5D']
            loc_name = { 'MCP1-1D': '1','MCP1-2D' :'2','MCP1-3D':'3','MCP1-4D':'4','MCP1-5D':'5' }
        else:
            print(meander, ' is not a valid meander name. MC and MZ are only valid meander names.')

        loc_colors = {'river': 'mediumblue', '1': cmaplist[0],'2':cmaplist[1],'3':cmaplist[2],'4':cmaplist[3],'5':cmaplist[4] }
        loc_symbols = {'river':'s', '1': 'o', '2': 'p','3': 'd','4': 'P', '5':'X' }

        for l in obs_locs:
            df = chem_obs[chem_obs['Well'] == l]
            for component in components:
                mask = df[component].isna()
                df = df[~mask]
                ax.plot(df['Date'], df[component]*factor, linestyle = '-.', linewidth = 0.5, color = loc_colors[loc_name[l]], marker = loc_symbols[loc_name[l]])
    except:
        print('No observations loaded -- plotting simulations results only.')    
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%-d-%b"))
    ax.set_xlabel('Date')
    ax.set_ylabel("SO$_{4}^{2-}$ " + r"$\rm({\mu}M)$")
    return ax


def plot_Fe(results,times,distances,startdate,ax,meander,chem_obs=None):
    components = ['Total_Fe++ [M]']
    for component in components:
        for distance in distances:
            df1 = results[distance][component]
            ax = pr.plot_time_series(df1, times, distance, discretization=0.5, ax=ax, unit='uM', startdate=startdate, meander=meander)
    try:
        components = ['Fe']
        factor = 1e6
        cmap = mpl.cm.get_cmap('viridis')
        cmaplist = [cmap(i) for i in np.arange(0,1,0.2)]

        if meander == 'MZ':
            obs_locs = ['MZT1-1D', 'MZT1-2D', 'MZT1-3D', 'MZT1-4D', 'MZT1-5D']
            loc_name = { 'MZT1-1D': '1','MZT1-2D' :'2','MZT1-3D':'3','MZT1-4D':'4','MZT1-5D':'5' }
        elif meander == 'MC':
            obs_locs = ['MCP1-1D', 'MCP1-2D', 'MCP1-3D', 'MCP1-4D', 'MCP1-5D']
            loc_name = { 'MCP1-1D': '1','MCP1-2D' :'2','MCP1-3D':'3','MCP1-4D':'4','MCP1-5D':'5' }
        else:
            print(meander, ' is not a valid meander name. MC and MZ are only valid meander names.')

        loc_colors = {'river': 'mediumblue', '1': cmaplist[0],'2':cmaplist[1],'3':cmaplist[2],'4':cmaplist[3],'5':cmaplist[4] }
        loc_symbols = {'river':'s', '1': 'o', '2': 'p','3': 'd','4': 'P', '5':'X' }

        for l in obs_locs:
            df = chem_obs[chem_obs['Well'] == l]
            for component in components:
                mask = df[component].isna()
                df = df[~mask]
                ax.plot(df['Date'], df[component]*factor, linestyle = '-.', linewidth = 0.5, color = loc_colors[loc_name[l]], marker = loc_symbols[loc_name[l]])
    except:
        print('No observations loaded -- plotting simulations results only.')
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%-d-%b"))
    ax.set_xlabel('Date')
    ax.set_ylabel('Fe (uM)')
    return ax



def plot_DOC(results,times,distances,startdate,ax,meander,chem_obs=None):
    components = ['Total_SOC(aq) [M]']
    for component in components:
        for distance in distances:
            df1 = results[distance][component]
            ax = pr.plot_time_series(df1, times, distance, discretization=0.5, ax=ax, unit='uM', startdate=startdate, meander=meander)
    try:
        components = ['NPOC']
        factor = 1e3
        cmap = mpl.cm.get_cmap('viridis')
        cmaplist = [cmap(i) for i in np.arange(0,1,0.2)]
        if meander == 'MZ':
            obs_locs = ['MZT1-1D', 'MZT1-2D', 'MZT1-3D', 'MZT1-4D', 'MZT1-5D']
            loc_name = { 'MZT1-1D': '1','MZT1-2D' :'2','MZT1-3D':'3','MZT1-4D':'4','MZT1-5D':'5' }
        elif meander == 'MC':
            obs_locs = ['MCP1-1D', 'MCP1-2D', 'MCP1-3D', 'MCP1-4D', 'MCP1-5D']
            loc_name = { 'MCP1-1D': '1','MCP1-2D' :'2','MCP1-3D':'3','MCP1-4D':'4','MCP1-5D':'5' }
        else:
            print(meander, ' is not a valid meander name. MC and MZ are only valid meander names.')
        loc_colors = {'river': 'mediumblue', '1': cmaplist[0],'2':cmaplist[1],'3':cmaplist[2],'4':cmaplist[3],'5':cmaplist[4] }
        loc_symbols = {'river':'s', '1': 'o', '2': 'p','3': 'd','4': 'P', '5':'X' }

        for l in obs_locs:
            df = chem_obs[chem_obs['Well'] == l]
            for component in components:
                mask = df[component].isna()
                df = df[~mask]
                ax.plot(df['Date'], df[component]*factor, linestyle = '-.', linewidth = 0.5, color = loc_colors[loc_name[l]], marker = loc_symbols[loc_name[l]])
    except:
        print('No observations loaded -- plotting simulations results only.')
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%-d-%b"))
    ax.set_xlabel('Date')
    ax.set_ylabel('DOC (uM)')
    return ax

def plot_tracer(results,distances,startdate,ax, meander):
    components = ['Total_Tracer [M]']
    for component in components:
        df1 = results[component]
        for distance in distances:
            ax = pr.plot_time_series(df1, distance, discretization=0.5, ax=ax, unit='uM', startdate=startdate, meander=meander)

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%-d-%b"))
    ax.set_xlabel('Date')
    return ax


def plot_oxygen(results,distances,startdate,ax, meander):
    components = ['Total_O2(aq) [M]']
    for component in components:
        df1 = results[component]
        for distance in distances:
            ax = pr.plot_time_series(df1, distance, discretization=0.5, ax=ax, unit='uM', startdate=startdate, meander=meander)

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%-d-%b"))
    ax.set_xlabel('Date')
    ax.set_ylabel('O2(aq) (uM)')
    return ax

def plot_nitrate(results,distances,startdate,ax,meander, chem_obs=None):
    components = ['Total_NO3- [M]']
    for component in components:
        df1 = results[component]
        for distance in distances:
            ax = pr.plot_time_series(df1, distance, discretization=0.5, ax=ax, unit='uM', startdate=startdate, meander=meander)
    try:
        components = ['NO3']
        factor = 1e3
        cmap = mpl.cm.get_cmap('viridis')
        cmaplist = [cmap(i) for i in np.arange(0,1,0.2)]

        if meander == 'MZ':
            obs_locs = ['MZT1-1D', 'MZT1-2D', 'MZT1-3D', 'MZT1-4D', 'MZT1-5D']
            loc_name = { 'MZT1-1D': '1','MZT1-2D' :'2','MZT1-3D':'3','MZT1-4D':'4','MZT1-5D':'5' }
        elif meander == 'MC':
            obs_locs = ['MCP1-1D', 'MCP1-2D', 'MCP1-3D', 'MCP1-4D', 'MCP1-5D']
            loc_name = { 'MCP1-1D': '1','MCP1-2D' :'2','MCP1-3D':'3','MCP1-4D':'4','MCP1-5D':'5' }
        else:
            print(meander, ' is not a valid meander name. MC and MZ are only valid meander names.')

        loc_colors = {'river': 'mediumblue', '1': cmaplist[0],'2':cmaplist[1],'3':cmaplist[2],'4':cmaplist[3],'5':cmaplist[4] }

        loc_symbols = {'river':'s', '1': 'o', '2': 'p','3': 'd','4': 'P', '5':'X' }

        for l in obs_locs:
            df = chem_obs[chem_obs['Well'] == l]
            for component in components:
                mask = df[component].isna()
                df = df[~mask]
                ax.plot(df['Date'], df[component]*factor, linestyle = '-.', linewidth = 0.5, color = loc_colors[loc_name[l]], marker = loc_symbols[loc_name[l]])
    except:
        print('No observations loaded -- plotting simulations results only.')
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%-d-%b"))
    ax.set_xlabel('Date')
    ax.set_ylabel("NO$_{3}$- " + r"$\rm({\mu}M)$")
    return ax


def plot_Ac(results,distances,startdate,ax,meander):
    components = ['Total_Ac- [M]']


    if meander == 'MZ':
        obs_locs = ['MZT1-1D', 'MZT1-2D', 'MZT1-3D', 'MZT1-4D', 'MZT1-5D']
        loc_name = { 'MZT1-1D': '1','MZT1-2D' :'2','MZT1-3D':'3','MZT1-4D':'4','MZT1-5D':'5' }
    elif meander == 'MC':
        obs_locs = ['MCP1-1D', 'MCP1-2D', 'MCP1-3D', 'MCP1-4D', 'MCP1-5D']
        loc_name = { 'MCP1-1D': '1','MCP1-2D' :'2','MCP1-3D':'3','MCP1-4D':'4','MCP1-5D':'5' }
    else:
        print(meander, ' is not a valid meander name. MC and MZ are only valid meander names.')

    for component in components:
        df1 = results[component]
        for distance in distances:
            ax = pr.plot_time_series(df1, distance, discretization=0.5, ax=ax, unit='uM', startdate=startdate, meander=meander)

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%-d-%b"))
    ax.set_xlabel('Date')
    ax.set_ylabel('Ac [uM]')
    return ax

def plot_HS(results,distances,startdate,ax,meander):
    components = ['Free_HS- [M]']
    for component in components:
        df1 = results[component]
        for distance in distances:
            ax = pr.plot_time_series(df1, distance, discretization=0.5, ax=ax, unit='uM', startdate=startdate, meander=meander)

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%-d-%b"))
    ax.set_xlabel('Date')
    ax.set_ylabel('HS- [uM]')
    return ax

def plot_minVF(results,distances,startdate,mineral,ax,meander):
    components = [mineral + '_VF [m^3 mnrl_m^3 bulk]']
    for component in components:
        df1 = results[component]
        for distance in distances:
            ax = pr.plot_time_series(df1, distance, discretization=0.5, ax=ax, unit='M', startdate=startdate, meander=meander)

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%-d-%b"))
    ax.set_xlabel('Date')
    ax.set_ylabel(mineral + ' [m^3 mnrl_m^3 bulk]')
    return ax

def plot_rxnRate(results,times,distances,startdate,rxn,ax,meander,reverse=False):
    components = [rxn]
    for component in components:
        for distance in distances:
            df1 = results[distance][component]
            ax = pr.plot_time_series(df1, times, distance, discretization=0.5, ax=ax, unit='M', startdate=startdate, meander=meander,reverse=reverse)
            #ax = pr.plot_time_series(df1, distance, discretization=0.5, ax=ax, unit='M', startdate=startdate, meander=meander,reverse=reverse)

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%-d-%b"))
    ax.set_xlabel('Date')
    ax.set_ylabel('Rate [mol_m^3-sec]')
    return ax


def label_panel(ax, xpltl, ypltl, lbl,fontsize):
    ax.text(xpltl, ypltl,lbl,
        horizontalalignment='center',
        verticalalignment='center',
        transform = ax.transAxes, fontweight='bold', fontsize = fontsize)


def makeLegend(fig,labels,xpos=1):
    from matplotlib.lines import Line2D
    cmap = mpl.cm.get_cmap('viridis')
    cmaplist = [cmap(i) for i in np.arange(0,1,0.2)]

    legcolors = [ cmaplist[0],cmaplist[1],cmaplist[2],cmaplist[3],cmaplist[4] ]
    custom_lines = [Line2D([0], [0], color=legcolors[0], lw=4),
                    Line2D([0], [0], color=legcolors[1], lw=4),
                    Line2D([0], [0], color=legcolors[2], lw=4),
                    Line2D([0], [0], color=legcolors[3], lw=4),
                    Line2D([0], [0], color=legcolors[4], lw=4)]

    fig.legend(custom_lines,labels, bbox_to_anchor = (xpos,0.5), loc = 'center', frameon = False, ncol=1 )