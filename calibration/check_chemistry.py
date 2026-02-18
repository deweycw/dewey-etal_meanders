#!/usr/bin/env python
"""
Compare the CHEMISTRY blocks of two PFLOTRAN input files.

Usage:
    python check_chemistry.py <run_directory>
    python check_chemistry.py <file1.in> <file2.in>

With one argument (a directory), the script finds the _spin.in and
transient .in files automatically.  With two arguments, it compares
the two files directly.
"""

import sys
import re
import difflib
from pathlib import Path


SECTION_HEADER = re.compile(r'^\s*#={3,}')


def extract_chemistry_block(filepath):
    """Extract lines between the CHEMISTRY and CONSTRAINTS section headers."""
    lines = filepath.read_text().splitlines()
    block = []
    inside = False

    for line in lines:
        if not inside:
            if SECTION_HEADER.match(line) and 'CHEMISTRY' in line.upper():
                inside = True
            continue

        if SECTION_HEADER.match(line) and 'CONSTRAINTS' in line.upper():
            break

        block.append(line.strip())

    if not block:
        raise ValueError(f"No CHEMISTRY block found in {filepath}")

    return block


def normalize(block):
    """Strip inline comments (! ...), then remove blank and comment-only lines."""
    out = []
    for l in block:
        l = l.split('!')[0].rstrip()
        if l and not l.startswith('#'):
            out.append(l)
    return out


def compare(file_a, file_b):
    """Extract, normalize, and diff the CHEMISTRY blocks of two files."""
    block_a = normalize(extract_chemistry_block(file_a))
    block_b = normalize(extract_chemistry_block(file_b))

    if block_a == block_b:
        print(f"OK — CHEMISTRY blocks match ({len(block_a)} lines)")
    else:
        print("MISMATCH — CHEMISTRY blocks differ:\n")
        diff = difflib.unified_diff(
            block_a, block_b,
            fromfile=file_a.name, tofile=file_b.name,
            lineterm='',
        )
        for line in diff:
            print(line)
        sys.exit(1)


def main():
    if len(sys.argv) == 2:
        # Directory mode: find spin and transient .in files
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

        compare(spin_files[0], trans_files[0])

    elif len(sys.argv) == 3:
        # Two-file mode: compare two .in files directly
        file_a = Path(sys.argv[1])
        file_b = Path(sys.argv[2])
        for f in (file_a, file_b):
            if not f.is_file():
                print(f"Error: {f} not found")
                sys.exit(1)

        compare(file_a, file_b)

    else:
        print(f"Usage: {sys.argv[0]} <run_directory>")
        print(f"       {sys.argv[0]} <file1.in> <file2.in>")
        sys.exit(1)


if __name__ == '__main__':
    main()
