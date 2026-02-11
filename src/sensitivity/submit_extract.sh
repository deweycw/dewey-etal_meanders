#!/bin/bash
#SBATCH --job-name=extract_sa
#SBATCH --output=extract_sa_%j.out
#SBATCH --error=extract_sa_%j.err
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mem=32G
#SBATCH --time=02:00:00
#SBATCH --mail-type=ALL
#SBATCH --mail-user=cdewey@udel.edu
#SBATCH --partition=standard

vpkg_require singularity 

CONTAINER=/lustre/dewey/sw/pflotran-postproc.sif
SENSITIVITY_DIR=/lustre/dewey/users/4315/sensitivity

singularity exec \
    --bind /lustre/dewey/users/4315/sensitivity:/work \
    "$CONTAINER" \
    python3 /work/extract_sa_results.py \
        --sensitivity-dir /work \
        --obs-csv /work/mc_2019_porewater.csv \
        --n-runs 340
