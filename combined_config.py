import os
import json

config_dir = 'config/'

all_entities_config = {}

# loop through each file in the config directory
for filename in os.listdir(config_dir):
    if filename.endswith('.json'):
        file_path = os.path.join(config_dir, filename)

        with open(file_path, 'r') as file:
            entity_config = json.load(file)
            entity_name = filename.replace('.json', '')
            all_entities_config[entity_name] = entity_config

all_entities_config = dict(sorted(all_entities_config.items()))
