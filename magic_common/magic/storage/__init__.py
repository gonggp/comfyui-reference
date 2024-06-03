import os
import logging
from urllib.parse import urlparse

from magic.storage.s3 import S3FileManager
from magic.storage.http import http_download_to_file


logger = logging.getLogger()


def fuzzy_download_to_file(url, target, create_folder=True, region=None, bucket=None):
    if create_folder:
        folder = os.path.dirname(target)
        os.makedirs(folder, exist_ok=True)

    parsed_url = urlparse(url)
    scheme = parsed_url.scheme
    if scheme == 's3':
        s3c = S3FileManager(region=region, bucket=bucket)
        bucket = parsed_url.netloc
        key = parsed_url.path.strip("/")
        return s3c.download_file(bucket=bucket, key=key, filepath=target),
    elif scheme in ('http', 'https'):
        return http_download_to_file(url, target, create_folder)
    logger.warning(f'Unsupported scheme: {scheme}')
    return None
