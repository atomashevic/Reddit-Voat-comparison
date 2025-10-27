import h5py
import sys
import numpy as np
import pandas as pd
import os

name = sys.argv[1]
window = int(sys.argv[2])
path = "results_ensemble/%s/window%s"%(name, window)

results_path = "results_best_core/"
os.makedirs(results_path, exist_ok=True)
filename = results_path+"%s_window%s_core_per.hdf5"%(name, window)

with h5py.File(filename, 'w') as F:
    for ltlim in range(0, 180-window+1):
        htlim = ltlim+window
        h5py_file = path+'/%s_%s-%sdays.hdf5'%(name, ltlim, htlim)
        with h5py.File(h5py_file, 'r') as W:
            mdl = []
            for r in range(50):
                m = np.array(W['mdl_%s'%r])
                mdl.append(m)
    

        id = np.argmin(mdl)
        with h5py.File(h5py_file, 'r') as W:
            nodes = np.array(W['labels_%s'%id])
            N = np.array(W['ns_%s'%id])
            L = np.array(W['ms_%s'%id])
            Lm = np.array(W['Ms_%s'%id])
        F["labels_%s-%sdays"%(ltlim, htlim)] = nodes
        F["ns_%s-%sdays"%(ltlim, htlim)] = N
        F["ms_%s-%sdays"%(ltlim, htlim)] = L
        F["Ms_%s-%sdays"%(ltlim, htlim)] = Lm

   

    #df = pd.DataFrame(nodes, columns = ['User', 'Group'])    
    #loc = 'results/%s/window%s'%(name, window)
    #os.makedirs(loc, exist_ok=True)
    #df.to_csv(loc+'/%s_labels_%s-%sdays.csv'%(name, ltlim, htlim), index=None)

    
