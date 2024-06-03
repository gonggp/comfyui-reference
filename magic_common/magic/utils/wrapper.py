import time
import logging
from functools import wraps

import requests

from magic.logger.magic_logger import MagicLogger


def retry(max_attempts=3, delay=1):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            attempts = 0
            while attempts < max_attempts:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    attempts += 1
                    logging.info(f'Attempt {attempts}/{max_attempts}, failed: {e}')
                    time.sleep(delay)
            raise Exception(f'Failed after {max_attempts} attempts')
        return wrapper
    return decorator


def safer(returns=None, silent=True):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception:
                if not silent:
                    logging.exception(f'Error raise when calling {func.__name__}, return {returns}')
                return returns
        return wrapper
    return decorator


def timer(name=None, callback=None, tags=None):
    tags = tags or {}
    def decorator(func):
        logger = MagicLogger.CUR_LOGGER or logging.getLogger()
        @wraps(func)
        def wrapper(*args, **kwargs):
            start = time.time()
            ret = func(*args, **kwargs)
            end = time.time()
            if tags:
                suffix = f'|| {"||".join([f"{k}={v}" for k, v in tags.items()])}'
            else:
                suffix = ''
            logger.info(f'MAGIC_METRICS Elapsed of {name or func.__name__}: {end - start} {suffix}')
            if callable(callback):
                callback(start, end, end-start)
            return ret
        return wrapper
    return decorator


def retry_for_requests(max_attempts=3, delay=1):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            attempts = 0
            while attempts < max_attempts:
                try:
                    resp = func(*args, **kwargs)
                    resp.raise_for_status()
                    return resp
                except requests.exceptions.HTTPError as e:
                    logging.warning(f'Request HTTP Error: {e}')
                    attempts += 1
                    time.sleep(delay)
                except requests.exceptions.Timeout:
                    logging.warning(f'Request TIMEOUT')
                    attempts += 1
                    time.sleep(delay)
                except requests.exceptions.ConnectionError:
                    logging.warning(f'Request CONNECTION ERROR')
                    attempts += 1
                    time.sleep(delay)
                except Exception as e:
                    attempts += 1
                    logging.info(f'Attempt {attempts}/{max_attempts}, failed: {e}')
                    time.sleep(delay)
            raise Exception(f'Failed after {max_attempts} attempts')
        return wrapper
    return decorator
