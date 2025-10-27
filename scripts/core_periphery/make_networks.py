import pandas as pd
import networkx as nx
import csv
import numpy as np
import sys
import os
import functions_helper as fh
import pandas as pd


if __name__ == '__main__':

    net = sys.argv[1]  # 'area51'
    name = sys.argv[2]
    window = int(sys.argv[3])
    nodes = 'all'             
    
    path='networks/%s/window%s'%(name, window)

    os.makedirs(path, exist_ok=True)
    #fname = path+'/%s_%s.hdf5'%(name, tip)

    loc='../'
    qa = pd.read_csv(loc+'/interactions/%s/%s/%s_interactions_questions_answers.csv'%(net,name,name))
    acc = pd.read_csv(loc+'/interactions/%s/%s/%s_interactions_acc_answers.csv'%(net,name,name))
    comm = pd.read_csv(loc+'/interactions/%s/%s/%s_interactions_comments.csv'%(net,name,name))
    time0 = 0
    time1 = window
    tip = 'qa_comm'
    
    

    for i in range(0, 200):
        ltlim = time0 + i
        htlim = time1 + i
        interactions = fh.merge_interactions(qa, acc, comm, ltlim, htlim, tip=tip)
        edges = fh.filter_edges(interactions)
        np.savetxt(path+'/%s_%s-%sdays.txt'%(name, ltlim, htlim), edges)


