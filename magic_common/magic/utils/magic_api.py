import requests

from magic.config import config
from magic.utils.wrapper import retry_for_requests


def safe_try_magic_api_token():
    try:
        return config.MAGIC_API_TOKEN
    except Exception:
        return None


@retry_for_requests()
def request(method, path, **kwargs):
    url = f'{config.MAGIC_API_HOST}{path}'
    magic_token = safe_try_magic_api_token()
    headers = kwargs.pop('headers', {})
    if magic_token:
        headers['Authorization'] = magic_token
    return requests.request(method, url, headers=headers, **kwargs)


def get(path, **kwargs):
    return request("get", path, **kwargs)


def post(path, **kwargs):
    return request("post", path, **kwargs)


def put(path, **kwargs):
    return request("put", path, **kwargs)


def patch(path, **kwargs):
    return request("patch", path, **kwargs)


def delete(path, **kwargs):
    return request("delete", path, **kwargs)


def options(path, **kwargs):
    return request("options", path, **kwargs)


def head(path, **kwargs):
    return request("head", path, **kwargs)
