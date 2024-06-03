import requests

from magic.config import config
from magic.logger.magic_logger import MagicLogger


def submit_new_task(payload, _logger=None):
    logger = _logger or MagicLogger.get_default_logger()

    url = f"{config.MAGIC_TASK_REPORT_API_BASE}/add_task"
    resp = requests.post(url, json=payload, timeout=10)
    logger.info(f'Submit new task to {url}, '
                f'resp status_code: {resp.status_code}, '
                f'resp_body: {resp.content}.')
    return resp


def retry_submit_new_task(payload, times=3, _silent=False, _logger=None):
    while times > 0:
        times = times - 1
        try:
            return submit_new_task(payload)
        except Exception as err:
            if not _silent:
                raise RuntimeError(f'Submit new task failed after retried') from err
            else:
                logger = _logger or MagicLogger.get_default_logger()
                logger.exception(f"err_info: {err}, retry left: {times}")


def report_task_number(payload, _logger=None):
    logger = _logger or MagicLogger.get_default_logger()

    url = f"{config.MAGIC_TASK_REPORT_API_BASE}/update_task_number"
    resp = requests.post(url, json=payload, timeout=10)
    logger.info(f'Update task number: {url}, '
                f'payload: {payload}. '
                f'resp status_code: {resp.status_code}, '
                f'resp_body: {resp.content}.')
    return resp


def retry_report_task_number(payload, times=3, _silent=False, _logger=None):
    while times > 0:
        times = times - 1
        try:
            return report_task_number(payload)
        except Exception as err:
            if not _silent:
                raise RuntimeError(f'Submit new task failed after retried') from err
            else:
                logger = _logger or MagicLogger.get_default_logger()
                logger.exception(f"err_info: {err}, retry left: {times}")
