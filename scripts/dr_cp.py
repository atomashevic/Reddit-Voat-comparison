from mrjob.job import MRJob
import json
import csv

class MRGroupReputation(MRJob):

    def configure_args(self):
        super(MRGroupReputation, self).configure_args()
        self.add_file_arg('--reputation-file')

    def mapper_init(self):
        self.reputations = {}
        with open(self.options.reputation_file, 'r') as f:
            for line in f:
                list_part, dict_part = line.split('\t')
                list_data = json.loads(list_part)
                username = list_data[0]
                dict_data = json.loads(dict_part)
                for day, reputation in dict_data.items():
                    self.reputations[(username, day)] = float(reputation)

    def mapper(self, _, line):
        day, json_part = line.split('\t')
        data = json.loads(json_part)
        labels = data["labels"]
        for username, group in labels.items():
            reputation = self.reputations.get((username, day))
            if reputation is not None and reputation > 1:
                yield (group, day), reputation

    def reducer(self, key, values):
        total = 0
        count = 0
        for value in values:
            total += value
            count += 1
        avg_reputation = total / count if count > 0 else 0
        # yield key, (avg_reputation, total, count)
        yield key, ','.join(map(str, (avg_reputation, total, count)))

if __name__ == '__main__':
    MRGroupReputation.run()
