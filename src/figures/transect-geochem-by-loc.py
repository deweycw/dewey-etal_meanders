# %%
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.cm as cm
import pandas as pd
from datetime import date, timedelta
from matplotlib.ticker import MultipleLocator, AutoMinorLocator
import seaborn as sns

svdir = '/Users/christiandewey/Library/CloudStorage/GoogleDrive-christian.w.dewey@gmail.com/My Drive/manuscripts/2023_Dewey-Fendorf-etal_meanders/plots/'
fdir = '/Users/christiandewey/Library/CloudStorage/GoogleDrive-christian.w.dewey@gmail.com/My Drive/manuscripts/2023_Dewey-Fendorf-etal_meanders/data'

plt.rc('font', size=8)
plt.rcParams['axes.labelsize'] = 10
plt.rcParams['mathtext.default'] = 'rm'
plt.rcParams['ytick.major.pad'] = '1.5'
plt.rcParams['xtick.major.pad'] = '0.5'

BWIDTH = 0.75
XPLTL = -0.25
YPLTL = 0.98


# %%
def make_panel(component, data, years, ax):
    sns.boxplot(
        x="trans_pos_m", y=component, data=data, ax=ax,
        width=BWIDTH, hue='year', showfliers=False, linewidth=0.8,
        palette=['dimgrey', 'gainsboro'], notch=False, showcaps=False,
        medianprops={"alpha": 0.0},
    )
    ax.set_xticklabels(ax.get_xticklabels(), rotation=90, horizontalalignment='center')
    ax.get_legend().remove()

    palette_y = ['viridis', 'rocket'] if 2017 in years else ['rocket', 'viridis']
    for year, offset, pal in zip(years, [-0.3, 0.3], palette_y):
        df = data[data['year'] == year].copy()
        df['CatPos'] = df['CatPos'] + offset
        sns.scatterplot(
            data=df, x='CatPos', y=component, hue='Date',
            palette=pal, size=4, ax=ax, edgecolor=None, legend=False,
        )
    ax.set_xlabel('Location')
    ax.yaxis.set_minor_locator(AutoMinorLocator())
    sns.despine()


def make_colorbars(years, fig):
    palette_y = ['viridis', 'rocket'] if 2017 in years else ['rocket', 'viridis']
    positions = [[1.00, 0.55, 0.02, 0.3], [1.0, 0.15, 0.02, 0.3]]

    for year, pal, pos in zip(years, palette_y, positions):
        cbar_ax = fig.add_axes(pos)
        mind = date(int(year), 5, 25)
        maxd = date(int(year), 10, 25)
        mindf, maxdf = mind.timetuple().tm_yday, maxd.timetuple().tm_yday
        norm = matplotlib.colors.Normalize(vmin=mindf, vmax=maxdf)
        sm = cm.ScalarMappable(norm=norm, cmap=pal)
        sm.set_array(np.arange(mindf, maxdf))
        cb = fig.colorbar(sm, orientation='vertical', cax=cbar_ax, shrink=0.5)
        cb_labels = [i.get_text() for i in cb.ax.get_yticklabels()]
        startdate = date(int(year), 1, 1)
        labels = [timedelta(days=float(d) - 1.0) + startdate for d in cb_labels]
        cb.ax.set_yticklabels([d.strftime("%-d %b %y") for d in labels], size=8)


def load_and_process(fname, site_prefix, positions, depth_filter=None):
    data = pd.read_csv(fdir + fname, parse_dates=['Date'])
    data['trans_pos_m'] = None

    for r in range(len(data)):
        w = data['Well'].iloc[r]
        if site_prefix in w:
            if depth_filter is not None and data['Depth name'].iloc[r] != depth_filter:
                continue
            data.loc[r, 'trans_pos_m'] = positions[w]

    sub = data[data['Well'].str.contains(site_prefix)].copy()
    sub['Ca_M'] = sub['Ca_M'] * 1e3
    sub['Fe_M'] = sub['Fe_M'] * 1e6
    sub['P_M'] = sub['P_M'] * 1e6
    sub['SO4_mM'] = sub['SO4_mM'] * 1e3
    sub['NO3_mM'] = sub['NO3_mM'] * 1e3
    sub['NH4_mM'] = sub['NH4_mM'] * 1e3
    sub['DOC_mM'] = sub['DOC_mM'] * 1e3
    return sub


def add_panel_labels(axes_labels):
    for ax, label in axes_labels:
        ax.text(XPLTL, YPLTL, label,
                horizontalalignment='center', verticalalignment='center',
                transform=ax.transAxes, fontweight='bold', fontsize=12)


def make_figure(data, years, savename):
    fig, ((ax1, ax3), (ax2, ax7), (ax5, ax8)) = plt.subplots(3, 2, figsize=(6, 8))

    make_panel('pH', data, years, ax1)
    ax1.set_ylabel('pH')
    ax1.yaxis.set_major_locator(MultipleLocator(1))
    ax1.set_ylim(6.6, 8.3)

    make_panel('Fe_M', data, years, ax2)
    ax2.set_ylabel('Fe (' + r'$\mu$M)')
    ax2.set_ylim(bottom=0)

    make_panel('NH4_mM', data, years, ax3)
    ax3.set_ylabel(r'NH$_4^{+}$ ($\mu$M)')
    ax3.set_ylim(bottom=0)

    make_panel('SO4_mM', data, years, ax7)
    ax7.set_ylabel(r'SO$_4^{2-}$ ($\mu$M)')
    ax7.set_ylim(bottom=-5)

    make_panel('DIC_mM', data, years, ax5)
    ax5.set_ylabel('DIC (mM)')
    ax5.yaxis.set_major_locator(MultipleLocator(1))
    ax5.set_ylim(bottom=0)

    make_panel('DOC_mM', data, years, ax8)
    ax8.set_ylabel('DOC (' + r'$\mu$M)')
    ax8.set_ylim(bottom=0)

    add_panel_labels([
        (ax1, 'a'), (ax3, 'b'), (ax2, 'c'),
        (ax7, 'd'), (ax5, 'e'), (ax8, 'f'),
    ])

    make_colorbars(years, fig)
    fig.tight_layout()
    plt.savefig(svdir + savename, bbox_inches='tight')


# %%
# MCP transect: 2017 vs 2018
mcp_positions = {
    'MCP1-1': 'MCP1', 'MCP1-2': 'MCP2', 'MCP1-3': 'MCP3',
    'MCP1-4': 'MCP4', 'MCP1-5': 'MCP5',
}
mcp_catpos = {'MCP1': 0, 'MCP2': 1, 'MCP3': 2, 'MCP4': 3, 'MCP5': 4}

sub17 = load_and_process('/porewater/mc_2017_porewater_ess-dive.csv', 'MCP', mcp_positions)
sub18 = load_and_process('/porewater/mc_2018_porewater_ess-dive.csv', 'MCP', mcp_positions)

mcp17_18 = pd.concat([sub17, sub18], ignore_index=True)
mcp17_18['year'] = mcp17_18['Date'].dt.year
mcp17_18['CatPos'] = mcp17_18['trans_pos_m'].map(mcp_catpos)

make_figure(mcp17_18, [2017, 2018], '/mcp_profiles_17_18_pH-NH4-DIC-Fe-DOC-SO4.pdf')

# %%
# MZA transect: 2018 vs 2019
mza_positions = {
    'MZT1-1-D': 'MZA1', 'MZT1-2-D': 'MZA2', 'MZT1-3-D': 'MZA3',
    'MZT1-4-D': 'MZA4', 'MZT1-5-D': 'MZA5',
}
mza_catpos = {'MZA1': 0, 'MZA2': 1, 'MZA3': 2, 'MZA4': 3, 'MZA5': 4}

sub18 = load_and_process('/porewater/mz_2018_porewater_ess-dive.csv', 'MZT1', mza_positions, depth_filter='Deep')
sub19 = load_and_process('/porewater/mz_2019_porewater_ess-dive_replica.csv', 'MZT1', mza_positions, depth_filter='Deep')

mza_18_19 = pd.concat([sub18, sub19], ignore_index=True)
mza_18_19['year'] = mza_18_19['Date'].dt.year
mza_18_19['CatPos'] = mza_18_19['trans_pos_m'].map(mza_catpos)

make_figure(mza_18_19, [2018, 2019], '/mza_profiles_18_19_pH-NH4-DIC-Fe-DOC-SO4.pdf')
