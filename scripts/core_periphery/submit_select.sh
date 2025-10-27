#!/bin/bash
#PBS -q standard
#PBS -l nodes=1:ppn=1
#PBS -e ${PBS_JOBID}.err
#PBS -o ${PBS_JOBID}.out
#PBS -l walltime=10:10:00:00

cd ${PBS_O_WORKDIR}
module load python/3.6.5
source .venv/bin/activate

python select_best_core.py ${name} ${window}
