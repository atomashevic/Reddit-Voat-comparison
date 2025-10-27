import pandas as pd
import networkx as nx
import gc
import sys
import json
from mrjob.job import MRJob
from mrjob.step import MRStep
import datetime
import numpy as np


class MeanDr(MRJob):

    def mapper(self, _, line):
        par, comm = line.split("\t")
        comm = json.loads(comm.strip())
        
        time0 = int(par.strip("[]").split(",")[1])


        time1 = int(par.strip("[]").split(",")[2])

        for key, val in comm.items():
            yield ([int(key), time0, time1], float(val))
        
    def reducer(self, key, values):
         ls = list(values)
         N = len([i for i in ls if i>=1])
         if N==0:
            R = 0
         else:
            R = np.mean([i for i in ls if i>=1])
         
         yield (key, [N, R])
    

    def steps(self):
        return [MRStep(mapper=self.mapper,
                       reducer=self.reducer),
               ]                     

if __name__ == '__main__':
      
     MeanDr.run()

        
        
        

        

