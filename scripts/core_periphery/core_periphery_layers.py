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

def write_results( results, fname, time0, time1, k,l):
    with h5py.File(fname, 'a') as W:
        for r in range(len(results)):
            
            #print (r)
            ltlim = k + time0 + r
            htlim = k + time1 + r
            if 'ns_%s-%sdays_%sgroups'%(ltlim, htlim, l) in W.keys():
                print(ltlim, htlim, 'calculated')
            else:
                #print( 'mdl', np.array(results[i][4]))
                W['labels_%s-%sdays_%sgroups'%(ltlim, htlim, l)] = np.array(list(results[r][0].items()))
                W['ns_%s-%sdays_%sgroups'%(ltlim, htlim, l)] = np.array(results[r][1])
                W['ms_%s-%sdays_%sgroups'%(ltlim, htlim, l)] = np.array(results[r][2])
                W['Ms_%s-%sdays_%sgroups'%(ltlim, htlim, l)] = np.array(results[r][3])
                W['mdl_%s-%sdays_%sgroups'%(ltlim, htlim, l)] = np.array(results[r][4])               
    

def mpi_run(edges, L):
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

    net = sys.argv[1]  # 'area51'
    name = sys.argv[2] # '052012astronomy'
    nproc = int(sys.argv[3])
    print(name)
    tip = 'qa_comm'
    nodes = 'all'             
    
    path='results_layers'

    os.makedirs(path, exist_ok=True)
    fname = path+'/%s_%s.hdf5'%(name, tip)

    loc='../'
    qa = pd.read_csv(loc+'/interactions/%s/%s/%s_interactions_questions_answers.csv'%(net,name,name))
    acc = pd.read_csv(loc+'/interactions/%s/%s/%s_interactions_acc_answers.csv'%(net,name,name))
    comm = pd.read_csv(loc+'/interactions/%s/%s/%s_interactions_comments.csv'%(net,name,name))
    time0 = 0
    time1 = 30
    data = []
    k = 0
    for i in range (k, 100):
        ltlim = time0 + i
        htlim = time1 + i
        interactions = fh.merge_interactions(qa, acc, comm, ltlim, htlim, tip=tip)
        edges = fh.filter_edges(interactions)
        data.append(edges)

    for Lg in range (2, 5):
        pool = Pool(nproc)
        p_mpi = partial(mpi_run, L=Lg)
        results = pool.map(p_mpi, data)
        write_results( results, fname, time0, time1, k, Lg)
