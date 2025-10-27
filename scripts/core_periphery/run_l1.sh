#!/bin/bash                                                                                       
                                                     
for net in "launched"
do
    for name in "economics" 
#name="052012astronomy"
      do
           qsub -v name=${name},net=${net} submit_l.sh     
      done
done                                 
                                                                                                  
