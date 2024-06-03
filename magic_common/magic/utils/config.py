import os
import logging

import yaml

from magic.config import config


def inject_os_envs_from_yaml_config(config_file):
    with open(config_file, 'r') as file:
        data = yaml.load(file, Loader=yaml.FullLoader)
    envs = data.get('envs')
    logging.info(f'Inject environment variable: {envs}')
    os.environ.update(envs)
    config.reload_from_envs()
