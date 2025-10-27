import pandas as pd
import numpy as np
import json

reputation_file = '../results/dynamical_reputations/videos_dr_inline'

def get_rep(username, day, file_path):
    day = str(day)
    with open(file_path, 'r') as f:
        for line in f:
            list_part, dict_part = line.split('\t')
            list_data = json.loads(list_part)
            dict_data = json.loads(dict_part)
            if list_data[0] == username:
                return dict_data[day]
    return "User not found"

cp_file = '../results/core_periphery/videos_core_periphery'

# load file and get number of lines
with open(cp_file, 'r') as f:
    cp_lines = f.readlines()
    cp_lines = len(cp_lines)

# print first line
# with open(cp_file, 'r') as f:
#     cp_line = f.readline()
#     print(cp_line)


# from each line get "ns": [x, y]" part, no json parsing
# with open(cp_file, 'r') as f:
#     for line in f:
#         ns = line.split('"ns": ')[1].split(']')[0]
#         print(ns)

# set days variable to be equal to the number of lines in the file
n_days = cp_lines

# prepare empty dataframe with the results, columns day = 30:days, core_reputation=0, periphery_reputation=0

results = pd.DataFrame(np.zeros((n_days, 3)), columns=['day', 'core_reputation', 'periphery_reputation'])

results['day'] = range(30, n_days+30)


with open(cp_file, 'r') as f:
    day = 0
    # iterate over lines in file
    # for line in f:
    # only first 5 lines
    for i in range(5):
      line = f.readline()
      print('Going through day ', day)
      labels = line.split('"labels": {')[1].split('}')[0]
      labels = labels.split(',')
      labels = [x.split(': ') for x in labels]
      labels = pd.DataFrame(labels, columns=['username', 'group'])
      for user in labels['username']:
        print('Going through user ', user)
        reputation = get_rep(user, day, reputation_file)
        # check if reputation is a number
        if reputation == 'User not found':
          continue
        else:
          reputation = float(reputation)
          if labels[labels['username'] == user]['group'] == 'core':
            results['core_reputation'][day] += reputation
          else:
            results['periphery_reputation'][day] += reputation
      day += 1

results.to_csv('../results/dynamical_reputations/videos_dr_core_periphery.csv', index=False)
