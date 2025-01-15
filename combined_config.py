import os

import yaml

config_dir = 'config/'

all_entities_config = {}

# loop through each file in the config directory
for filename in os.listdir(config_dir):
    if filename.endswith('.yaml'):
        file_path = os.path.join(config_dir, filename)

        try:
            # Attempt to open and load the JSON file
            with open(file_path, 'r') as file:
                #print(f"YAML reading: {file}")
                entity_config = yaml.safe_load(file)
                entity_name = filename.replace('.yaml', '')
                all_entities_config[entity_name] = entity_config
        except FileNotFoundError:
            print(f"Error: File {file_path} not found.")
        except yaml.YAMLError:
            print(f"Error: Failed to decode YAML in file {file_path}.")
        except Exception as e:
            print(f"An unexpected error occurred while processing {file_path}: {e}")

all_entities_config = dict(sorted(all_entities_config.items()))
