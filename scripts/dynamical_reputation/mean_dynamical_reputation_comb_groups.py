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

def user_group(user_id, user_df):
    # group 1: registered before 2014-05-09
    # group 2: registered after 2014-05-09 but before 2015-06-06
    # group 3: registered after 2015-06-06 but before 2016-11-23
    # group 4: registered after 2016-11-23 but before 2018-03-15
    # group 5: registered after 2018-03-15
    # if not in user_df return NA
    if user_id not in user_df.user.values:
        return(np.nan)
    else:
        if user_df[user_df['user']==user_id].reg_date_utc.values[0] < 1399593600:
            return(1)
        elif user_df[user_df['user']==user_id].reg_date_utc.values[0] < 1433558400:
            return(2)
        elif user_df[user_df['user']==user_id].reg_date_utc.values[0] < 1479840000:
            return(3)
        elif user_df[user_df['user']==user_id].reg_date_utc.values[0] < 1521081600:
            return(4)
        else:
            return(5)

class MeanDr(MRJob):

    def configure_args(self):
        super(MeanDr, self).configure_args()
        self.add_passthru_arg('--target_group', help='Target group argument')

    def mapper(self, _, line):
        target_group = self.options.target_group
        par, comm = line.split("\t")
        comm = json.loads(comm.strip())
        user = par.strip("[]").split(",")[0]
        user = user.strip('"')
        group = user_group(user, user_df)
        time0 = int(par.strip("[]").split(",")[1])
        time1 = int(par.strip("[]").split(",")[2])
        if group == target_group:
            for key, val in comm.items():
                yield ([int(key), time0, time1], float(val))
    
    def combiner(self, key, values):
        ls = list(values)
        N = len([i for i in ls if i>=1 ])
        if N==0:
           R = 0
        else:
           R = sum([i for i in ls if i>=1])
        yield( key, [N, R])

    def reducer(self, key, values):
        ls = list(values)
        N = sum([i[0] for i in ls])
        if N==0:
           R = 0
        else:
           R = sum([i[1] for i in ls])/N

        yield (key, [N, R])

        
    #def reducer(self, key, values):
    #     ls = list(values)
    #     N = len([i for i in ls if i>=1])
    #     if N==0:
    #        R = 0
    #     else:
    #        R = np.mean([i for i in ls if i>=1])
    #     
    #     yield (key, [N, R])
    

    def steps(self):
        return [MRStep(mapper=self.mapper,
                       combiner=self.combiner,
                       reducer=self.reducer),
               ]                     

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='My MRJob script')
    parser.add_argument('reputation', help='Reputation file')
    parser.add_argument('target_group', help='Target group argument')
    args = parser.parse_args()
    user_df = pd.read_json("../data/users/user_profiles.ndjson", lines=True)
    user_df['reg_date_utc'] = pd.to_datetime(user_df["reg_date"])
    user_df['reg_date_utc'] = user_df['reg_date_utc'].apply(lambda x: x.timestamp())
    mr_job = MeanDr(args=['-r', 'local', args.reputation])
    mr_job.options.target_group = args.target_group
    with mr_job.make_runner() as runner:
        runner.run()


