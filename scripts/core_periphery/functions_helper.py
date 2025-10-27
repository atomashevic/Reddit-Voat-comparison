import pandas as pd
import networkx as nx
import numpy as np
import collections

def merge_interactions(interactions, acc, comm, ltlim, htlim, tip='qa'):
    
    if tip=='qa':
        
        i1 = interactions[(interactions['days']<htlim)&(interactions['days']>=ltlim)]
        a1 = acc[(acc['days']<htlim)&(acc['days']>=ltlim)]
        
        it = pd.concat([ i1[['PostUserId', 'RespondUserId', 'QId', 'days']], a1[['PostUserId', 'RespondUserId', 'QId', 'days']],])
        it = it[it['PostUserId']!=it['RespondUserId']]
        
        return it.dropna()
    else:
        if tip=='comments':
            
            c = comm[(comm['days']<htlim)&(comm['days']>=ltlim)]
            it = pd.concat([ c[['PostUserId', 'RespondUserId', 'QId', 'days']],])
            #it = it[it['PostUserId']!=it['RespondUserId']]
            
            return it.dropna()
        else:
            if tip=='qa_comm':
                
                i1 = interactions[(interactions['days']<htlim)&(interactions['days']>=ltlim)]
                a1 = acc[(acc['days']<htlim)&(acc['days']>=ltlim)]
                c = comm[(comm['days']<htlim)&(comm['days']>=ltlim)]
                
                it = pd.concat([ i1[['PostUserId', 'RespondUserId', 'QId', 'days']], a1[['PostUserId', 'RespondUserId', 'QId', 'days']], c[['PostUserId', 'RespondUserId', 'QId', 'days']],])
                it = it[it['PostUserId']!=it['RespondUserId']]
                return it.dropna()
            else:
                
                print('ERROR')
                return 'None'
            
def filter_edges(df):
    df = df.reset_index()
    edges = [ ((df.loc[i][1]), (df.loc[i][2])) for i in range(0, len(df))]
    #print(len(pd.concat([df['PostUserId'], df['RespondUserId']]).unique()))
    return edges

def edges_w(edges):

    edges_sorted = []
    for i in edges:
        if i[0]< i[1]:
            edges_sorted.append((i[0], i[1]))
        else:
            edges_sorted.append((i[1], i[0]))
    
    return collections.Counter(edges_sorted)


def filter_nodes(interactions, acc, comm, ltlim, htlim, nodes='all', tip='qa'):
    i1 = interactions[(interactions['days']<=htlim)&(interactions['days']>=ltlim)]
    a1 = acc[(acc['days']<=htlim)&(acc['days']>=ltlim)]
    c = comm[(comm['days']<=htlim)&(comm['days']>=ltlim)]
    
    if ((nodes=='all') and (tip== 'qa')) or ((nodes=='all') and (tip== 'comments')) or ((nodes=='all') and (tip== 'qa_comm')) :
        
        n = np.sort(pd.concat([ i1['PostUserId'], i1['RespondUserId'], a1['PostUserId'], a1['RespondUserId'], c['PostUserId'], c['RespondUserId']]).dropna().unique())
        
        return n
    else:
        
        if ((nodes=='active') and (tip== 'qa')):
            
            n = np.sort(pd.concat([ i1['PostUserId'], i1['RespondUserId'], a1['PostUserId'], a1['RespondUserId'],]).dropna().unique())
            return n
        else:
            
            if ((nodes=='active') and (tip== 'comments')):
                
                n = np.sort(pd.concat([ i1['PostUserId'], i1['RespondUserId'], a1['PostUserId'], a1['RespondUserId'],]).dropna().unique())
                
                return n
                
            else: 
                print('ERROR')
                return "None"
