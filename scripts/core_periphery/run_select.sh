#!/bin/bash                                                                                       
for window in 10 60
do                                                      
    for name in "astronomy" #"052012astronomy" "physics" "economics"  "literature"  "052012-theoretical-physics" "052012-literature"  "052012economics"
      do
           qsub -v name=${name},window=${window} submit_select.sh     
      done
done                                 
                                                                                                 

