import pandas as pd
import networkx as nx
import csv
import numpy as np
import h5py
from multiprocessing import Pool, cpu_count
import sys
import os
from core_periphery_sbm import core_periphery as cp
from core_periphery_sbm import network_helper as nh
from core_periphery_sbm import model_fit as mf
import functions_helper as fh
from functools import partial


def run_sbm(G):
    hubspoke = cp.HubSpokeCorePeriphery(n_gibbs=100, n_mcmc=10*len(G))
    #H=hubspoke.clean_network(G)
    hubspoke.infer(G)
    labels = hubspoke.get_labels(last_n_samples=50, prob=False, return_dict=True)

    #model selection
    inf_labels_hs = hubspoke.get_labels(last_n_samples=50, prob=False, return_dict=False)
    mdl_hubspoke = mf.mdl_hubspoke(G, inf_labels_hs, n_samples=100000)
    #print(mdl_hubspoke)
    return labels, mdl_hubspoke

def run_layered(G, L):

    layered = cp.LayeredCorePeriphery(n_layers=L, n_gibbs=100, n_mcmc=10*len(G))
    layered.infer(G)
    layered_labels = layered.get_labels(last_n_samples=50, prob=False, return_dict=True)
    
    #model selection
    inf_labels_l = layered.get_labels(last_n_samples=50, prob=False, return_dict=False)
    mdl_layered = mf.mdl_layered(G, inf_labels_l, n_layers=L, n_samples=100000)
    #print ('layered', mdl_layered)
    return layered_labels, mdl_layered

def mpi_run(edges, L):
    np.random.seed()
    G = nx.Graph()
    G.add_edges_from(edges)  
    if L==2:
    
        labels, mdl = run_sbm(G)
        ns, ms, Ms = nh.get_block_stats(G, labels, n_blocks=2)
        #return labels, ns, ms, Ms, mdl
    else:
        labels, mdl = run_layered(G, L)
        ns, ms, Ms = nh.get_block_stats(G, labels, n_blocks=L)
    return labels, ns, ms, Ms, mdl


if __name__ == '__main__':

    name = sys.argv[1] # '052012astronomy'
    ltlim = int(sys.argv[2])
    htlim = int(sys.argv[3])
    window = int(sys.argv[4])
    nproc = int(sys.argv[5])
    
    path='results_ensemble/%s/window%s'%(name, window)
    os.makedirs(path, exist_ok=True)
    

    edge_file = 'networks/%s/window%s/%s_%s-%sdays.txt'%(name,window, name, ltlim, htlim)
    edges = np.loadtxt(edge_file)
    pool = Pool(nproc)
    p_mpi = partial(mpi_run, L=2)
    data = [edges for i in range(50)]
    results = pool.map(p_mpi, data)

    fname = path+'/%s_%s-%sdays.hdf5'%(name, ltlim, htlim)

    with h5py.File(fname, 'a') as W:
        for r in range(len(results)):
            if 'ns_%s'%(r) in W.keys():
                print('exists')
            else:
                W['labels_%s'%(r)] = np.array(list(results[r][0].items()))
                W['ns_%s'%(r)] = np.array(results[r][1])
                W['ms_%s'%(r)] = np.array(results[r][2])
                W['Ms_%s'%(r)] = np.array(results[r][3])
                W['mdl_%s'%(r)] = np.array(results[r][4])
