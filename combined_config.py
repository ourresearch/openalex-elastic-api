import os
import json

config_dir = 'config/'

all_entities_config = {}

# loop through each file in the config directory
for filename in os.listdir(config_dir):
    if filename.endswith('.json'):
        file_path = os.path.join(config_dir, filename)

        try:
            # Attempt to open and load the JSON file
            with open(file_path, 'r') as file:
                entity_config = json.load(file)
                entity_name = filename.replace('.json', '')
                all_entities_config[entity_name] = entity_config
        except FileNotFoundError:
            print(f"Error: File {file_path} not found.")
        except json.JSONDecodeError:
            print(f"Error: Failed to decode JSON in file {file_path}.")
        except Exception as e:
            print(f"An unexpected error occurred while processing {file_path}: {e}")

all_entities_config = dict(sorted(all_entities_config.items()))
