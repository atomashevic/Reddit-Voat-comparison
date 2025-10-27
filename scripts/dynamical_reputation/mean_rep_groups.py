import pandas as pd
import networkx as nx
import gc
import sys
import json
from mrjob.job import MRJob
from mrjob.step import MRStep
import datetime
import numpy as np
import argparse

def user_group(reg_time):

    if reg_time<1399593600:
        return 1
    elif reg_time<1433558400:
        return 2
    elif reg_time<1479840000:
        return 3
    elif reg_time< 1521081600:
        return 4
    else:
        return 5

class MeanDr(MRJob):
   
    def configure_args(self):
        #ovde ucitamo dodatni parametar, koju grupu selektujemo
        super(MeanDr, self).configure_args()
        self.add_passthru_arg('--target_group', help="Target group")    

    def mapper(self, _, line):
        # ovaj maper dobija linije iz dva fajla koja su drugacije formatirana, pa zato imamo dve grane
        # user_info fajl se sastoji od json linija, tu cemo kao key selectovati user, i kao val vratiti kada je registrovan korisnik
        # za drugi fajl, isto kao key vraticemo user, i val je dict sa njegovim reputacijama
        try:
           
           data = json.loads(line)
           
           yield str(data["user"]).strip('"'), {"registered": data["reg_date"]}
        
        except:
        
        
            par, comm = line.split("\t")
            comm = json.loads(comm.strip())
            user = par.strip("[]").split(",")[0]
            user = user.strip('"')
         
            time0 = int(par.strip("[]").split(",")[1])
            time1 = int(par.strip("[]").split(",")[2])
            yield user, {"time0": time0, "time1": time1,"reputation": comm}

    def reducer(self, key, values):
        # reducer ce sada imati key=user, val=[{registered:}, {"reputation":, "time0":, "time1": }]
        # prvo cemo ovu listu dict spojiti u jedan dict results
        vals = list(values)
        results = {}
        keys = []
        for dict_res in vals:
            for feat, feat_res in dict_res.items():
                results[feat] = feat_res
                keys.append(feat)
               
        
        # iz nekod razloga neki useri za koje imamo reputacije se ne nalaze u user_info fajlu, zato zelim da selectujem samo usere za koje imam sve podatke i reg date i reputacije
        if ("reputation" in results) and ("registered" in results):
          
            reg_date_utc = pd.to_datetime(results["registered"]).timestamp()
            group = int(user_group(reg_date_utc))
            target_group = int(self.options.target_group)
       
            #selektujemo grupu korisnika i ukoliko se poklapa sa target grupom vratiti reputaciju
            if  group==target_group:
                yield key, results
   
    def mapper2(self, user, results):
        #ovaj maper je sada isti kao u prethodnoj verziji, key> [dan, prvi vremenski trenutak, poslednji vremenski trenutak ], val> vrednost reputacije u datom danu
        for key, val in results["reputation"].items():
         
            yield([int(key), results["time0"], results["time1"]], float(val) )

        
    def reducer2(self, key, values):

       # ovaj reducer skupi sve reputacije za odredjeni dan, i onda mozemo da izracunamo broj usera i srednju reputaciju za odredjeni dan
       # konacno dobijamo [dan, prvi vremeski trenutak, poslednji vremenski trenutak], [broj aktivnih korisnika, reputacija]

        ls = list(values)
        N = len([i for i in ls if i>1])
        if N==0:
           R = 0
        else:
           R = sum([i for i in ls if i>=1])/N
        yield (key, [N, R])

    def steps(self):
        return [MRStep(mapper=self.mapper,
                       reducer = self.reducer),
                MRStep(mapper=self.mapper2,
                       reducer=self.reducer2)]

if  __name__ == '__main__':
    MeanDr.run()
    

