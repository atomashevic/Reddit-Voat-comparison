#!/bin/bash
#PBS -q standard
#PBS -l nodes=1:ppn=8
#PBS -e ${PBS_JOBID}.err
#PBS -o ${PBS_JOBID}.out

cd ${PBS_O_WORKDIR}
module load python/3.6.5
source .venv/bin/activate

python core_periphery.py ${net} ${name} 8
