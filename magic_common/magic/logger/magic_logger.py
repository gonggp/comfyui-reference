import os
import logging
from logging.handlers import RotatingFileHandler

from magic.config import config
from magic.utils.misc import get_root_path


LOG_FORMAT = "%(asctime)s %(pathname)s[line:%(lineno)d] %(levelname)-8s %(message)s"
LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"


def get_log_level():
    LOG_LEVEL = config.MAGIC_LOG_LEVEL
    log_level = logging.INFO
    if LOG_LEVEL == 'DEBUG':
        log_level = logging.DEBUG
    elif LOG_LEVEL == 'INFO':
        log_level = logging.INFO
    elif LOG_LEVEL == 'WARNING' or LOG_LEVEL == 'WARN':
        log_level = logging.WARNING
    elif LOG_LEVEL == 'ERROR':
        log_level = logging.ERROR
    elif LOG_LEVEL == 'CRITICAL':
        log_level = logging.CRITICAL
    elif LOG_LEVEL == 'FATAL':
        log_level = logging.FATAL
    elif LOG_LEVEL == 'NOTSET':
        log_level = logging.NOTSET
    return log_level


def setup_basic_logging_config():
    log_level = get_log_level()
    log_path = str(os.path.join(get_root_path(), config.MAGIC_LOG_PATH))
    if log_path:
        logging.basicConfig(
            level=log_level,
            format=LOG_FORMAT,
            datefmt=LOG_DATEFMT,
            filename=log_path,
            filemode='a',
        )
        logging.info(f'Set log level: {log_level}, output to file: {log_path}')
    else:
        logging.basicConfig(
            level=log_level,
            format=LOG_FORMAT,
            datefmt=LOG_DATEFMT,
        )
        logging.info(f'Set log level: {log_level}, output to console')


def get_rotate_handler(max_bytes=204800, backup_count=50):
    log_path = config.MAGIC_LOG_PATH or '/tmp/magic_log.log'
    rotate_handler = RotatingFileHandler(
        filename=log_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
    )
    return rotate_handler


class MagicLogger(object):

    LOGGER_NAME = "magic_logger"
    CUR_LOGGER = None
    LOG_ATTRS = ['project_id', 'flow_id', 'user_id', 'task_id']

    def __init__(self, **kwargs):
        self.project_id = kwargs.pop('project_id', None)
        self.flow_id = kwargs.pop('flow_id', None)
        self.user_id = kwargs.pop('user_id', None)
        self.task_id = kwargs.pop('task_id', None)

        log_level = kwargs.pop('log_level', None)
        self._logger = logging.getLogger(f"{MagicLogger.LOGGER_NAME}")
        self._logger.addFilter(self._log_filter)
        self._logger.setLevel(log_level or get_log_level())

        MagicLogger.CUR_LOGGER = self

    @classmethod
    def get_default_logger(cls):
        return MagicLogger.CUR_LOGGER or logging.getLogger(MagicLogger.LOGGER_NAME)

    @property
    def _log_suffix(self):
        fields = []
        for field in self.LOG_ATTRS:
            value = getattr(self, field, None)
            if value is not None:
                fields.append(f'{field}={value}')
        return f'|| {" ".join(fields)}'

    def _log_filter(self, record):
        pathname = record.pathname
        if len(pathname) > 50:
            pathname = '~{}'.format(pathname[-50:])
        record.pathname = pathname
        return record

    def debug(self, msg, *args, **kwargs):
        msg = f'{msg} {self._log_suffix}'
        return self._logger.debug(msg, *args, **kwargs)

    def info(self, msg, *args, **kwargs):
        msg = f'{msg} {self._log_suffix}'
        return self._logger.info(msg, *args, **kwargs)

    def warn(self, msg, *args, **kwargs):
        msg = f'{msg} {self._log_suffix}'
        return self._logger.warn(msg, *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        msg = f'{msg} {self._log_suffix}'
        return self._logger.warning(msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        msg = f'{msg} {self._log_suffix}'
        return self._logger.error(msg, *args, **kwargs)

    def critical(self, msg, *args, **kwargs):
        msg = f'{msg} {self._log_suffix}'
        return self._logger.critical(msg, *args, **kwargs)

    def exception(self, msg, *args, **kwargs):
        msg = f'{msg} {self._log_suffix}'
        return self._logger.exception(msg, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._logger, name)

    def __del__(self):
        self._logger.removeFilter(self._log_filter)
        MagicLogger.CUR_LOGGER = None
