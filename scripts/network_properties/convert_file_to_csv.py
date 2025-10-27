import json
import sys
import pandas as pd
import numpy as np

def read_file(input_file, twin):
    
    with open(input_file, "r") as fp:
       data = []
       for line in fp:
           num, res = line.split("\t")
            
           res = json.loads(res)
           res["day"] = int(num)     
           data.append(res)
    T = res["Firstday"]
    
    data_csv = pd.DataFrame.from_dict(data)
    data_csv = data_csv.sort_values(by="day", ignore_index=True)
    M = int(max(data_csv["day"]))
    new_index = np.arange(0, max(data_csv["day"]))
    
    data_csv = data_csv.set_index("day").reindex(new_index).reset_index()
    data_csv["Firstday"]=T
    data_csv = data_csv.fillna(0)

    data_csv = data_csv[data_csv["day"]< (M-twin)]
    

    data_csv["First_Time"] = (pd.to_datetime(data_csv["Firstday"], unit="s") + pd.to_timedelta(data_csv['day'],'d'))
    
    return data_csv

input_file = sys.argv[1]
twin=int(sys.argv[2])
out_file=sys.argv[3]
data = read_file(input_file, twin)
data.to_csv(out_file, index=None) 
