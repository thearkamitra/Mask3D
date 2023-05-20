#!/bin/bash
#SBATCH -n 24                     # 24 cores
#SBATCH --time 40:00:00                   # 8-hour run-time
#SBATCH --mem-per-cpu=4000     # 4000 MB per core
#SBATCH  --output=sbatch_log/%j.out
#SBATCH  --error=sbatch_err/%j.out
#SBATCH --mail-type=END,FAIL

cd /cluster/project/infk/cvg/students/amitra/thesis/Mask3D            # Change directory
export PYTHONPATH=.   
source ~/3dv/bin/activate               
python scripts/new_pipeline.py --use_rgb --superglue -w -d "$@" # Execute the program