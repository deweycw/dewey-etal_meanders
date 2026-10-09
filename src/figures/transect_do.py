# %%
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.cm as cm
import pandas as pd
from pathlib import Path
from datetime import date, timedelta
from matplotlib.ticker import AutoMinorLocator
import seaborn as sns

repo_root = Path(__file__).resolve().parents[2] if '__file__' in dir() else Path.cwd().parents[1]
svdir = repo_root / 'figures'
svdir.mkdir(exist_ok=True)
data_dir = repo_root / 'data' / 'observational'

plt.rc('font', size=8)
plt.rcParams['axes.labelsize'] = 10
plt.rcParams['mathtext.default'] = 'rm'
plt.rcParams['ytick.major.pad'] = '1.5'
plt.rcParams['xtick.major.pad'] = '0.5'

BWIDTH = 0.75
XPLTL = -0.1
YPLTL = 1.05

# DO conversion: 1 mg/L ≈ 31.25 µM (MW O2 = 32 g/mol)
MGL_TO_UM = 1e3 / 32.0


# %%
def load_do(fname, positions, do_col='DO', do_scale=1.0):
    """Load porewater CSV and extract DO at mapped transect positions."""
    data = pd.read_csv(data_dir / fname, parse_dates=['Date'])
    data['trans_pos_m'] = data['Well'].map(positions)
    sub = data[data['trans_pos_m'].notna()].copy()
    sub['DO_uM'] = sub[do_col] * do_scale
    sub = sub[sub['DO_uM'].notna()]
    return sub


def make_site_panel(site_data, years, catpos, ax, title):
    """Draw boxplot + date-colored scatter for one or two years."""
    site_data = site_data.copy()
    site_data['year'] = site_data['Date'].dt.year
    site_data['CatPos'] = site_data['trans_pos_m'].map(catpos)
    label_order = sorted(catpos, key=catpos.get)

    if len(years) == 1:
        sns.boxplot(
            x='trans_pos_m', y='DO_uM', data=site_data, ax=ax,
            order=label_order,
            width=BWIDTH, showfliers=False, linewidth=0.8,
            color='gainsboro', notch=False, showcaps=False,
            medianprops={'alpha': 0.0}, zorder=1,
        )
        offsets, palettes = [0.0], ['viridis']
    else:
        sns.boxplot(
            x='trans_pos_m', y='DO_uM', data=site_data, ax=ax,
            order=label_order,
            width=BWIDTH, hue='year', showfliers=False, linewidth=0.8,
            palette=['dimgrey', 'gainsboro'], notch=False, showcaps=False,
            medianprops={'alpha': 0.0}, zorder=1,
        )
        ax.get_legend().remove()
        offsets, palettes = [-0.3, 0.3], ['rocket', 'viridis']

    ax.set_xticklabels(ax.get_xticklabels(), rotation=90, ha='center')
    for year, offset, pal in zip(years, offsets, palettes):
        df = site_data[site_data['year'] == year].copy()
        df['CatPos'] = df['CatPos'] + offset
        sns.scatterplot(
            data=df, x='CatPos', y='DO_uM', hue='Date',
            palette=pal, size=4, ax=ax, edgecolor=None, legend=False,
            zorder=10,
        )

    # Mark locations with no data
    present = set(site_data['trans_pos_m'].unique())
    for label in label_order:
        if label not in present:
            idx = catpos[label]
            ax.text(idx, ax.get_ylim()[1] * 0.5, 'no data',
                    ha='center', va='center', fontsize=7, color='0.5',
                    fontstyle='italic')

    ax.set_xlabel('Location')
    ax.set_ylim(bottom=0)
    ax.yaxis.set_minor_locator(AutoMinorLocator())
    ax.set_title(title, fontsize=10)
    sns.despine(ax=ax)


LOC_LABELS = ['Loc 1', 'Loc 2', 'Loc 3', 'Loc 4', 'Loc 5']
loc_map = {
    'MCP1': 'Loc 1', 'MCP2': 'Loc 2', 'MCP3': 'Loc 3', 'MCP4': 'Loc 4', 'MCP5': 'Loc 5',
    'MZA1': 'Loc 1', 'MZA2': 'Loc 2', 'MZA3': 'Loc 3', 'MZA4': 'Loc 4', 'MZA5': 'Loc 5',
}
combined_catpos = {f'Loc {i+1}': i for i in range(5)}


def make_combined_panel(data, ax):
    """Boxplot by site + date-colored scatter (MCP viridis, MZA rocket)."""
    sns.boxplot(
        x='location', y='DO_uM', data=data, ax=ax,
        order=LOC_LABELS, width=BWIDTH, hue='site', showfliers=False,
        linewidth=0.8, palette=['dimgrey', 'gainsboro'], notch=False,
        showcaps=False, medianprops={'alpha': 0.0}, zorder=1,
    )
    ax.set_xticklabels(ax.get_xticklabels(), rotation=90, ha='center')
    ax.get_legend().remove()

    for site, offset, pal in [('MCP', -0.3, 'viridis'), ('MZA', 0.3, 'rocket')]:
        df = data[data['site'] == site].copy()
        df['CatPos'] = df['CatPos'] + offset
        sns.scatterplot(
            data=df, x='CatPos', y='DO_uM', hue='Date',
            palette=pal, size=4, ax=ax, edgecolor=None, legend=False,
            zorder=10,
        )
    ax.set_xlabel('Location')
    ax.set_ylabel(r'DO ($\mu$M)')
    ax.set_ylim(bottom=0)
    ax.yaxis.set_minor_locator(AutoMinorLocator())
    sns.despine(ax=ax)


def add_combined_colorbars(year, fig):
    """Two colorbars for MCP (viridis) and MZA (rocket)."""
    for pal, label, pos in [('viridis', 'MCP', [1.00, 0.55, 0.015, 0.3]),
                             ('rocket', 'MZA', [1.00, 0.15, 0.015, 0.3])]:
        cbar_ax = fig.add_axes(pos)
        mind, maxd = date(int(year), 5, 25), date(int(year), 10, 25)
        mindf, maxdf = mind.timetuple().tm_yday, maxd.timetuple().tm_yday
        norm = matplotlib.colors.Normalize(vmin=mindf, vmax=maxdf)
        sm = cm.ScalarMappable(norm=norm, cmap=pal)
        sm.set_array(np.arange(mindf, maxdf))
        cb = fig.colorbar(sm, orientation='vertical', cax=cbar_ax)
        cb.ax.invert_yaxis()
        cb_labels = [i.get_text() for i in cb.ax.get_yticklabels()]
        startdate = date(int(year), 1, 1)
        labels = [timedelta(days=float(d) - 1.0) + startdate for d in cb_labels]
        cb.ax.set_yticklabels([d.strftime("%-d %b %y") for d in labels], size=7)
        cb.ax.set_title(label, size=8, rotation=0)


def add_date_colorbar(year, fig, pos, palette='viridis'):
    """Add a date colorbar to the figure."""
    cbar_ax = fig.add_axes(pos)
    mind, maxd = date(int(year), 5, 25), date(int(year), 10, 25)
    mindf, maxdf = mind.timetuple().tm_yday, maxd.timetuple().tm_yday
    norm = matplotlib.colors.Normalize(vmin=mindf, vmax=maxdf)
    sm = cm.ScalarMappable(norm=norm, cmap=palette)
    sm.set_array(np.arange(mindf, maxdf))
    cb = fig.colorbar(sm, orientation='vertical', cax=cbar_ax)
    cb.ax.invert_yaxis()
    cb_labels = [i.get_text() for i in cb.ax.get_yticklabels()]
    startdate = date(int(year), 1, 1)
    labels = [timedelta(days=float(d) - 1.0) + startdate for d in cb_labels]
    cb.ax.set_yticklabels([d.strftime("%-d %b %y") for d in labels], size=8)
    cb.ax.set_title(str(year), size=9)


# %%
# ── Well positions (deep wells only) ──
mza_positions = {
    'MZT1-1-D': 'MZA1', 'MZT1-2-D': 'MZA2', 'MZT1-3-D': 'MZA3',
    'MZT1-4-D': 'MZA4', 'MZT1-5-D': 'MZA5',
    'MZT1-1D': 'MZA1', 'MZT1-2D': 'MZA2', 'MZT1-3D': 'MZA3',
    'MZT1-4D': 'MZA4', 'MZT1-5D': 'MZA5',
}
mza_catpos = {'MZA1': 0, 'MZA2': 1, 'MZA3': 2, 'MZA4': 3, 'MZA5': 4}

# MCP piezometers are single-depth (deep); names vary by year
mcp_positions = {
    'MCP1-1': 'MCP1', 'MCP1-2': 'MCP2', 'MCP1-3': 'MCP3',
    'MCP1-4': 'MCP4', 'MCP1-5': 'MCP5',
    'MCP1-1D': 'MCP1', 'MCP1-2D': 'MCP2', 'MCP1-3D': 'MCP3',
    'MCP1-4D': 'MCP4', 'MCP1-5D': 'MCP5',
}
mcp_catpos = {'MCP1': 0, 'MCP2': 1, 'MCP3': 2, 'MCP4': 3, 'MCP5': 4}

# ── Load data ──
# MZA: DO in mg/L in raw CSVs → convert to µM
mza18 = load_do('porewater/mz_2018_porewater.csv', mza_positions,
                 do_col='DO', do_scale=MGL_TO_UM)
mza19 = load_do('porewater/mz_2019_porewater.csv', mza_positions,
                 do_col='DO', do_scale=MGL_TO_UM)

# MCP: DO only in ess-dive files (already µM); no DO data for 2019
mcp17 = load_do('porewater/mc_2017_porewater_ess-dive.csv', mcp_positions,
                 do_col='DO_uM', do_scale=1.0)
mcp18 = load_do('porewater/mc_2018_porewater_ess-dive.csv', mcp_positions,
                 do_col='DO_uM', do_scale=1.0)


# %%
# ── Figure 1: MCP 2017 ──
fig, ax = plt.subplots(1, 1, figsize=(3.5, 3.5))

make_site_panel(mcp17, [2017], mcp_catpos, ax, 'MCP')
ax.set_ylabel(r'DO ($\mu$M)')

fig.tight_layout()
add_date_colorbar(2017, fig, [1.00, 0.15, 0.02, 0.7])
plt.savefig(svdir / 'do_transect_mcp_2017.png', bbox_inches='tight', dpi=200)


# %%
# ── Figure 2: 2018  (MCP + MZA combined) ──
mcp18_c = mcp18.copy()
mza18_c = mza18.copy()
mcp18_c['site'] = 'MCP'
mza18_c['site'] = 'MZA'
combined_2018 = pd.concat([mcp18_c, mza18_c], ignore_index=True)
combined_2018['location'] = combined_2018['trans_pos_m'].map(loc_map)
combined_2018['CatPos'] = combined_2018['location'].map(combined_catpos)

fig, ax = plt.subplots(1, 1, figsize=(3.5, 3.5))
make_combined_panel(combined_2018, ax)

fig.tight_layout()
add_combined_colorbars(2018, fig)
plt.savefig(svdir / 'do_transect_2018.png', bbox_inches='tight', dpi=200)


# %%
# ── Figure 3: 2019  (MZA only — no MCP DO data for 2019) ──
fig, ax = plt.subplots(1, 1, figsize=(3.5, 3.5))

make_site_panel(mza19, [2019], mza_catpos, ax, 'MZA')
ax.set_ylabel(r'DO ($\mu$M)')

fig.tight_layout()
add_date_colorbar(2019, fig, [1.00, 0.15, 0.02, 0.7])
plt.savefig(svdir / 'do_transect_2019.png', bbox_inches='tight', dpi=200)
