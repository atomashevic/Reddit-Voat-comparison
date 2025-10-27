#!/bin/bash                                                                                       


for window in 10 60
do                                                      
for net in "launched"
do
    for name in "physics" "economics" "astronomy" "literature" 
      do
           qsub -v name=${name},net=${net},window=${window} submit_net.sh     
      done
done                                 
                                                                                                 

for net in "area51"
do
    for name in "052012-theoretical-physics" "052012economics" "052012astronomy" "052012-literature"
      do
           qsub -v name=${name},net=${net},window=${window} submit_net.sh
      done
done
done 
