import json
import logging


logger = logging.getLogger()


def safe_load_json(raw):
    try:
        return json.loads(raw)
    except json.decoder.JSONDecodeError:
        logger.exception(f'Failed to decode JSON {raw}')
        return raw
