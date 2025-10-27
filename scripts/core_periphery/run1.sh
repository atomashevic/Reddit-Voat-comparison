#!/bin/bash                                                                                       
                                                     
for net in "launched"
do
    for name in  "aviation" "mathematica" "ell" "english" "japanese" "spanish" "french" "chinese" "german" "russian" "korean" "conlang" "esperanto" "italian" "latin" "portuguese" "ukranian"



 
#name="052012astronomy"
      do
           qsub -v name=${name},net=${net} submit.sh     
      done
done                                 
                                                                                                  
