#!/bin/bash                                                                                       
                                                     
for window in 10 60
do
for name in "astronomy"  #"economics" "052012economics" "astronomy" "052012astronomy" "economics" "052012economics" "literature" "052012-literature" "052012-theoretical-physics" "physics" 

do
    for k in {0..170}
    do
	ltlim=$((0+$k))
        htlim=$(($window+$k))
        qsub -v name=${name},ltlim=${ltlim},htlim=${htlim},window=${window} submit_ensemble.sh     
    done
done 
done                              
                                                                                                  
