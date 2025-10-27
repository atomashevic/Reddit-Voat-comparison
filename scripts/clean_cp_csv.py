import pandas as pd
import argparse

parser = argparse.ArgumentParser()

parser.add_argument('filename', type=str, help='The filename to process')

args = parser.parse_args()


df = pd.read_csv(args.filename, header = None)

cs = ['Group', 'Day', 'ActiveU', 'TotalReputation', 'AvgReputation']

if len(df.columns) == 6:
    print('File already clean!')
else:
    df.columns = ['Group','Day','TotalReputation','ActiveU']
    df['Group']= df['Group'].str.replace('[', '').astype(int)
    df[['Day', 'AvgReputation']] = df['Day'].str.split('\\]\\t', expand=True)
    df['Day'] = df['Day'].str.replace('"', '').astype(int)
    df['ActiveU'] = df['ActiveU'].str.replace('"','').astype(int)
    df['AvgReputation'] = df['AvgReputation'].str.replace('"','').astype(float)
    df = df[['Group', 'Day', 'ActiveU', 'TotalReputation', 'AvgReputation']]
    df = df.sort_values('Day')
    df.to_csv(args.filename)
    print('Done! CSV %s cleaned!' %(args.filename))