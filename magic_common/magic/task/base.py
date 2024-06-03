import enum
import json
import logging

import requests

from magic.config import config
from magic.metrics.client import MetricClient
from magic.logger.magic_logger import MagicLogger


DEFAULT_TIMEOUT = 10


class TaskStatus(enum.Enum):
    START = 'start'
    FINISH = 'finish'
    ERROR = 'error'


class TaskBase(object):

    TASK_TYPE = ''

    @classmethod
    def from_sqs_message(cls, message):
        attrs = message.get('Attributes', {})
        body = message.get('Body')
        payload = json.loads(body)
        return cls(
            project_id=payload.get('project_id'),
            flow_id=payload.get('flow_id'),
            user_id=payload.get('user_id'),
            task_id=payload.get('task_id'),
            body=body,
            attrs=attrs,
        )

    def __init__(self, **kwargs):
        self.project_id = kwargs.pop('project_id', None)
        self.flow_id = kwargs.pop('flow_id', None)
        self.user_id = kwargs.pop('user_id', None)
        self.task_id = kwargs.pop('task_id', None)
        self.attrs = kwargs.pop('attrs', {})
        self.msg_body = kwargs.pop('body', None)
        self.logger = MagicLogger(
            project_id=self.project_id,
            flow_id=self.flow_id,
            user_id=self.user_id,
            task_id=self.task_id,
            level=logging.INFO,
        )
        region = kwargs.get('region', None)
        region = region or config.AWS_REGION
        self.metric = MetricClient(
            region=region,
            namespace='ExecTime',
            task_type=self.TASK_TYPE,
        )

    @property
    def _get_task_report_host(self):
        return config.MAGIC_TASK_REPORT_API_BASE

    def _report_task_status(self, status, addition_payload=None, timeout=DEFAULT_TIMEOUT):
        if not self.project_id:
            self.logger.info(f'Empty project_id, skip report task status')
            return None

        addition_payload = addition_payload or {}
        payload = {
            'type': self.TASK_TYPE,
            'project_id': self.project_id,
            'flow_id': self.flow_id,
            'user_id': self.user_id,
            'task_id': self.task_id,
            'status': status,
            **addition_payload,
        }
        resp = requests.post(
            f'{self._get_task_report_host}/update_task_status',
            json=payload,
            timeout=timeout,
        )
        self.logger.info(f'report task status: {status}, '
                         f'status_code: {resp.status_code}')
        return resp

    def is_dropped_out(self, enqueue_timestamp=None):
        enqueue_timestamp = enqueue_timestamp or self.attrs.get('SentTimestamp')
        if not enqueue_timestamp:
            self.logger.warning(f'enqueue_timestamp is None')
            return False
        try:
            enqueue_timestamp = int(enqueue_timestamp) / 1000
            resp = requests.post(
                f'{self._get_task_report_host}/task_eligible_check',
                json={
                    'project_id': self.project_id,
                    'enqueue_time': str(enqueue_timestamp),
                }
            )
            return resp.status_code != 200
        except Exception:
            self.logger.exception(f'failed to handle `is_dropped_out`')
        return False

    def report_task_status_with_retry(self, status, addition_payload=None, timeout=DEFAULT_TIMEOUT, retries=3):
        while retries > 0:
            try:
                resp = self._report_task_status(
                    status,
                    addition_payload=addition_payload,
                    timeout=timeout
                )
                if resp is None:
                    return
                resp.raise_for_status()
                return resp
            except requests.exceptions.HTTPError as e:
                self.logger.exception(
                    f'failed report `{status}` error: STATUS_CODE '
                    f'URL={e.request.url}, '
                    f'STATUS_CODE={e.response.status_code}, '
                    f'BODY={e.response.text}'
                )
                retries = retries - 1
            except requests.exceptions.Timeout:
                self.logger.exception(f'failed report `{status}` error: TIMEOUT')
                retries = retries - 1
            except requests.exceptions.ConnectionError:
                self.logger.exception(f'failed report `{status}` error: CONNECTION')
                retries = retries - 1
            except Exception as e:
                self.logger.exception(f'Failed to request')
                raise e

    def mark_start(self, timeout=DEFAULT_TIMEOUT, retries=3):
        return self.report_task_status_with_retry(
            TaskStatus.START.value, timeout=timeout, retries=retries
        )

    def mark_finish(self, timeout=DEFAULT_TIMEOUT, retries=3):
        return self.report_task_status_with_retry(
            TaskStatus.FINISH.value, timeout=timeout, retries=retries
        )

    def mark_error(self, error_code=None, timeout=DEFAULT_TIMEOUT, retries=3):
        self.metric.count(metric_name='ERROR_COUNT')
        return self.report_task_status_with_retry(
            TaskStatus.ERROR.value,
            addition_payload={'error_code': error_code},
            timeout=timeout,
            retries=retries
        )

    def extract_param(self, sqs_msg):
        body = json.loads(sqs_msg.get('Body', ''))
        return body

    def process_task(self, body):
        raise NotImplemented()

    def __del__(self):
        self.logger.__del__()
