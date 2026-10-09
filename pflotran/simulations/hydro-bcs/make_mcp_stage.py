#!/usr/bin/env python3
"""
Build MCP river-stage boundary files from the MZT stage record.

There is no stage logger at MCP, so MCP river levels are derived from the
MZT upstream/downstream loggers. The relationship is defined in absolute
elevations (m ASL) so it does not depend on either grid's model datum:

    MCP_up(t) = MZT_up(t) + REACH_OFFSET
    MCP_dn(t) = MCP_up(t) + (MZT_dn(t) - MZT_up(t) - EXTRA_DROP) * MCP_LEN / MZT_LEN

i.e. the MCP head drop is the MZT head drop plus EXTRA_DROP, scaled from the
MZT logger spacing to the MCP transect length. Inputs and outputs are in each
grid's model coordinates (z = m ASL - datum).

This reproduces the 2019 files previously built by dwn_bc_creator_MC.ipynb and
applies the same recipe to 2018 using the MZT no-dam record (MBA well levels
near MCP track the no-dam series, not the dam-affected one).

Usage:
    python make_mcp_stage.py
"""

from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent

MZT_DATUM = 2721.5     # m ASL, z=0 of the MZT grid
MCP_DATUM = 2757.5     # m ASL, z=0 of the MCP grid
REACH_OFFSET = 36.30   # m, MCP upstream river level minus MZT upstream river level
EXTRA_DROP = 0.6       # m, added to the MZT head drop (assumed extra fall at MC)
MZT_LEN = 52.0         # m, spacing used for the MZT gradient
MCP_LEN = 61.0         # m, MCP transect length (122 cells x 0.5 m)

# (MZT upstream file, MZT downstream file, MCP upstream out, MCP downstream out)
YEARS = {
    '2019': ('hydro_us_2019_4-21_10-2-MZT.txt', 'hydro_ds_2019_4-21_10-2-MZT.txt',
             'mc_up_2019_3993h.txt', 'mc_dn_2019_3993h.txt'),
    '2018': ('mzt-NODAM_us_2018_4-1_10-31-MZT.txt', 'mzt-NODAM_ds_2018_4-1_10-31-MZT.txt',
             'mc_us_2018_5131h-NODAM.txt', 'mc_dn_2018_5131h-NODAM.txt'),
}

HEADER = 'TIME_UNITS h\nDATA_UNITS m\n!h\tx\ty\tz\n'


def read_stage(path):
    return pd.read_csv(path, sep=r'\s+', skiprows=3, header=None,
                       usecols=[0, 1, 2, 3], names=['h', 'x', 'y', 'z'])


def write_stage(path, df, z):
    with open(path, 'w') as f:
        f.write(HEADER)
        for h, x, y, zi in zip(df['h'], df['x'], df['y'], z):
            f.write(f'{h:.5E}\t{x:.5E}\t{y:.5E}\t{zi:.5E}\n')


def main():
    for year, (mzt_up_f, mzt_dn_f, mcp_up_f, mcp_dn_f) in YEARS.items():
        up = read_stage(HERE / mzt_up_f)
        dn = read_stage(HERE / mzt_dn_f)
        if not up['h'].equals(dn['h']):
            raise ValueError(f'{year}: MZT upstream/downstream times differ')

        mzt_up = up['z'] + MZT_DATUM
        mzt_dn = dn['z'] + MZT_DATUM
        mcp_up = mzt_up + REACH_OFFSET
        mcp_dn = mcp_up + (mzt_dn - mzt_up - EXTRA_DROP) * MCP_LEN / MZT_LEN

        write_stage(HERE / mcp_up_f, up, mcp_up - MCP_DATUM)
        write_stage(HERE / mcp_dn_f, up, mcp_dn - MCP_DATUM)
        print(f'{year}: {mcp_up_f}, {mcp_dn_f}  '
              f't0 up {mcp_up.iloc[0] - MCP_DATUM:.3f} dn {mcp_dn.iloc[0] - MCP_DATUM:.3f} (model z)')


if __name__ == '__main__':
    main()
