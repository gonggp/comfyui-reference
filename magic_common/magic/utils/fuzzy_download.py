import os
from typing import Optional
from urllib.parse import urlparse

from magic.storage import S3FileManager
from magic.logger.magic_logger import MagicLogger
from magic.storage.http import http_download, http_download_to_file


def fuzzy_download(uri, region=None, _logger=None):
    logger = _logger or MagicLogger.get_default_logger()
    parsed_url = urlparse(uri)
    scheme = parsed_url.scheme
    if scheme == 's3':
        s3c = S3FileManager(region=region)
        bucket = parsed_url.netloc
        file_key = parsed_url.path.strip("/")
        return s3c.download_obj(
            file_key=file_key,
            bucket=bucket,
        )
    elif scheme in ('http', 'https'):
        return http_download(uri)

    logger.warning(f'Unsupported scheme: {scheme}')
    return None


def fuzzy_download_to_file(uri, local_filepath, create_folder=True, region=None, _logger=None) -> Optional[str]:
    logger = _logger or MagicLogger.get_default_logger()

    if create_folder:
        folder = os.path.dirname(local_filepath)
        os.makedirs(folder, exist_ok=True)

    parsed_url = urlparse(uri)
    scheme = parsed_url.scheme

    if scheme == 's3':
        s3c = S3FileManager(region=region)
        bucket = parsed_url.netloc
        file_key = parsed_url.path.strip("/")

        return s3c.download_to_file(
            bucket=bucket,
            file_key=file_key,
            local_filepath=local_filepath
        )

    elif scheme in ('http', 'https'):
        return http_download_to_file(uri, local_filepath)

    logger.warning(f'Unsupported scheme: {scheme}')
    return None


def retry_fuzzy_download_to_file(*args, **kwargs) -> Optional[str]:
    silent = kwargs.pop('_silent', False)
    times = kwargs.pop('times', 3)
    while times > 0:
        times = times - 1
        try:
            return fuzzy_download_to_file(*args, **kwargs)
        except Exception as err:
            if not silent:
                raise RuntimeError(f'Download file failed after retried') from err
            else:
                _logger = kwargs.pop('_logger', None)
                logger = _logger or MagicLogger.get_default_logger()
                logger.exception(f"err_info: {err}, retry left: {times}")


def fuzzy_download_to_folder(uri, local_folder, create_folder=True, region=None, _logger=None) -> Optional[str]:
    filename = os.path.basename(uri)
    path = os.path.join(local_folder, filename)
    return fuzzy_download_to_file(uri, path, create_folder, region, _logger)


def retry_fuzzy_download_to_folder(*args, **kwargs) -> Optional[str]:
    silent = kwargs.pop('_silent', False)
    times = kwargs.pop('times', 3)
    while times > 0:
        times = times - 1
        try:
            return fuzzy_download_to_folder(*args, **kwargs)
        except Exception as err:
            if not silent:
                raise RuntimeError(f'Download file failed after retried') from err
            else:
                _logger = kwargs.pop('_logger', None)
                logger = _logger or MagicLogger.get_default_logger()
                logger.exception(f"err_info: {err}, retry left: {times}")
