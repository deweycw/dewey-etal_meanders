#!/usr/bin/env python
"""
Compare the CHEMISTRY blocks of the spin and transient PFLOTRAN input
files found in a run directory.

Usage:
    python check_chemistry.py <run_directory>

The script expects exactly two .in files: one ending in _spin.in (spin-up)
and one without that suffix (transient).  It extracts the CHEMISTRY … END
block from each and reports whether they match.
"""

import sys
import re
from pathlib import Path


def extract_chemistry_block(filepath):
    """Return the CHEMISTRY … END block as a list of stripped lines."""
    text = filepath.read_text()
    # Match from a line starting with CHEMISTRY to its closing END,
    # tracking nesting depth via block-opening keywords and END/slash.
    lines = text.splitlines()
    inside = False
    depth = 0
    block = []

    # PFLOTRAN block-opening keywords that increment depth
    block_openers = re.compile(
        r'^\s*(CHEMISTRY|PRIMARY_SPECIES|SECONDARY_SPECIES|GAS_SPECIES|'
        r'PASSIVE_GAS_SPECIES|MINERALS|MINERAL_KINETICS|GENERAL_REACTION|'
        r'MICROBIAL_REACTION|REACTION_SANDBOX|SORPTION|DATABASE|'
        r'OUTPUT|LOG_FORMULATION|IMMOBILE_SPECIES|DECOUPLED_EQUILIBRIUM_REACTIONS|'
        r'TRUNCATE_CONCENTRATION|ACTIVITY_COEFFICIENTS|MOLAL|'
        r'RADIOACTIVE_DECAY_REACTION|COLLOID_TRANSPORT|'
        r'REACTION_NETWORK|OPERATOR_SPLITTING)\b', re.IGNORECASE
    )

    for line in lines:
        stripped = line.strip()

        if not inside:
            if re.match(r'^\s*CHEMISTRY\b', line):
                inside = True
                depth = 1
                block.append(stripped)
            continue

        block.append(stripped)

        # Check for nested block openers (skip the initial CHEMISTRY)
        if block_openers.match(line) and depth >= 1 and stripped.upper() != 'CHEMISTRY':
            depth += 1

        # A bare END or / closes the current block level
        if stripped == 'END' or stripped == '/':
            depth -= 1
            if depth == 0:
                break

    if not block:
        raise ValueError(f"No CHEMISTRY block found in {filepath}")

    return block


def normalize(block):
    """Remove blank lines and comment-only lines for comparison."""
    return [l for l in block if l and not l.startswith('!') and not l.startswith('#')]


def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <run_directory>")
        sys.exit(1)

    run_dir = Path(sys.argv[1])
    if not run_dir.is_dir():
        print(f"Error: {run_dir} is not a directory")
        sys.exit(1)

    in_files = sorted(run_dir.glob('*.in'))
    spin_files = [f for f in in_files if f.stem.endswith('_spin')]
    trans_files = [f for f in in_files if not f.stem.endswith('_spin')]

    if len(spin_files) != 1 or len(trans_files) != 1:
        print(f"Error: expected 1 spin and 1 transient .in file, "
              f"found {len(spin_files)} spin and {len(trans_files)} transient")
        sys.exit(1)

    spin_file = spin_files[0]
    trans_file = trans_files[0]

    spin_block = extract_chemistry_block(spin_file)
    trans_block = extract_chemistry_block(trans_file)

    spin_norm = normalize(spin_block)
    trans_norm = normalize(trans_block)

    if spin_norm == trans_norm:
        print(f"OK — CHEMISTRY blocks match ({len(spin_norm)} lines)")
    else:
        print("MISMATCH — CHEMISTRY blocks differ:\n")
        import difflib
        diff = difflib.unified_diff(
            spin_norm, trans_norm,
            fromfile=spin_file.name, tofile=trans_file.name,
            lineterm='',
        )
        for line in diff:
            print(line)
        sys.exit(1)


if __name__ == '__main__':
    main()
