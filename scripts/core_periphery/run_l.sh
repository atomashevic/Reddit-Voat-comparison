#!/bin/bash                                                                                       
                                                     
for net in "area51"
do
    for name in "052012economics" 
#name="052012astronomy"
      do
           qsub -v name=${name},net=${net} submit_l.sh     
      done
done                                 
                                                                                                  
