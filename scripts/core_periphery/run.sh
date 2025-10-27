#!/bin/bash                                                                                       
                                                     
for net in "launched"
do
    for name in "languagelearning" 
#name="052012astronomy"
      do
           qsub -v name=${name},net=${net} submit.sh     
      done
done                                 
                                                                                                  
