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
from mrjob.job import MRJob

class CorePeripheryMRJob(MRJob):

    def run_sbm(self, G):
        hubspoke = cp.HubSpokeCorePeriphery(n_gibbs=100, n_mcmc=10*len(G))
        # H=hubspoke.clean_network(G)
        hubspoke.infer(G)
        labels = hubspoke.get_labels(last_n_samples=50, prob=False, return_dict=True)
        return labels

    def write_results(self, results, fname, time0, time1, k):
        with h5py.File(fname, 'a') as W:
            for r in range(len(results)):
                # print (r)
                ltlim = k + time0 + r
                htlim = k + time1 + r
                if 'ns_%s-%sdays' % (ltlim, htlim) in W.keys():
                    print(lltim, htlim, 'calculated')
                else:
                    # print(ltlim, htlim)
                    W['labels_%s-%sdays' % (ltlim, htlim)] = np.array(list(results[r][0].items()))
                    W['ns_%s-%sdays' % (ltlim, htlim)] = np.array(results[r][1])
                    W['ms_%s-%sdays' % (ltlim, htlim)] = np.array(results[r][2])
                    # W['Ms'] = np.array(results[i][3])

    def mapper(self, _, line):
        edges = line.split(',')
        G = nx.Graph()
        G.add_edges_from(edges)
        labels = self.run_sbm(G)
        ns, ms, Ms = nh.get_block_stats(G, labels, n_blocks=2)
        yield None, (labels, ns, ms, Ms)

    def reducer(self, _, values):
        results = list(values)
        path = 'results'
        os.makedirs(path, exist_ok=True)
        fname = path + '/%s_%s.hdf5' % (name, tip)
        self.write_results(results, fname, time0, time1, k)


if __name__ == '__main__':
    net = sys.argv[1]  # 'area51'
    name = sys.argv[2]  # '052012astronomy'
    nproc = int(sys.argv[3])
    print(name)
    tip = 'qa_comm'
    nodes = 'all'

    loc = '../'
    qa = pd.read_csv(loc + '/interactions/%s/%s/%s_interactions_questions_answers.csv' % (net, name, name))
    acc = pd.read_csv(loc + '/interactions/%s/%s/%s_interactions_acc_answers.csv' % (net, name, name))
    comm = pd.read_csv(loc + '/interactions/%s/%s/%s_interactions_comments.csv' % (net, name, name))
    time0 = 0
    time1 = 30
    data = []
    k = 0
    for i in range(k, 200):
        ltlim = time0 + i
        htlim = time1 + i
        interactions = fh.merge_interactions(qa, acc, comm, ltlim, htlim, tip=tip)
        edges = fh.filter_edges(interactions)
        data.append(edges)

    job = CorePeripheryMRJob(args=[path])
    with job.make_runner() as runner:
        runner.run()

    write_results(results, fname, time0, time1, k)
