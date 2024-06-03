import io
import os
import sys
import time
import socket
import logging
import traceback
from typing import Type
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

import requests

from magic.config import config
from magic.aws.instance import get_instance_rebalance_recommendations, get_instance_action
from magic.notification.wechat import async_send_wx_markdown_message
from magic.task.base import TaskBase
from magic.task.error import TaskError
from magic.queue.sqs import SQSClient
from magic.utils.signal import GracefulInterruptHandler
from magic.utils.wrapper import safer


STOP_FILE = "/tmp/stop-magic-worker"


def format_exception(ei):
    sio = io.StringIO()
    tb = ei[2]
    traceback.print_exception(ei[0], ei[1], tb, None, sio)
    s = sio.getvalue()
    sio.close()
    if s[-1:] == "\n":
        s = s[:-1]
    return s


class MagicWorker(object):

    DEFAULT_REBALANCE_TIME_THRESHOLD = 5 * 60

    def __init__(self, task_cls: Type[TaskBase], queue_url, rebalence_threshold=None, region=None):
        region = region or config.AWS_REGION
        self.task_cls = task_cls
        self.queue_url = queue_url
        self.logger = logging.getLogger('magic.worker')
        self.sqs_client = SQSClient(region=region, queue_url=queue_url)
        self._is_check_scheduled_terminate = False
        self.is_auto_task_report_start = True
        self.is_auto_task_report_finish = True
        self.is_auto_task_report_error = True
        self.is_delete_sqs_message_when_error = False

        self.task_concurrency = 1

        self.rebalence_threshold = rebalence_threshold or self.DEFAULT_REBALANCE_TIME_THRESHOLD

        self.allow_task_types = []

        # Metrics
        self.boot_time = None
        self.task_count = {
            'success': 0,
            'failed': 0, # biz error
            'error': 0, # un-catch errors
        }

    def disable_task_report_start(self, is_report=False):
        self.is_auto_task_report_start = is_report

    def disable_task_report_finish(self, is_report=False):
        self.is_auto_task_report_finish = is_report

    def disable_task_report_error(self, is_report=False):
        self.is_auto_task_report_error = is_report

    def enable_check_scheduled_terminate(self, is_check=True):
        self._is_check_scheduled_terminate = is_check

    def set_delete_message_when_error(self, is_delete=True):
        self.is_delete_sqs_message_when_error = is_delete

    def set_task_concurrency(self, task_concurrency=1):
        self.task_concurrency = task_concurrency

    @safer(returns=False)
    def _is_scheduled_terminate(self):
        rebalance_recommendations = get_instance_rebalance_recommendations()
        instance_action_time = get_instance_action()
        if rebalance_recommendations is None and instance_action_time is None:
            return False

        utcnow = datetime.utcnow()
        is_ready_to_stop = (rebalance_recommendations - utcnow) < timedelta(seconds=self.rebalence_threshold)
        if is_ready_to_stop:
            self.logger.warning(f'Spot instance rebalance recommendations: {rebalance_recommendations}')
            return True

        is_ready_to_stop = (instance_action_time - utcnow) < timedelta(seconds=self.rebalence_threshold)
        if is_ready_to_stop:
            self.logger.warning(f'Spot instance action: {instance_action_time}')
            return True

    @safer(returns=False)
    def _has_trigger_stop(self):
        return os.path.isfile(STOP_FILE)

    def set_allow_task_types(self, task_types):
        self.allow_task_types = task_types

    def report_error_to_wx(self, title=None, exc_info=None, extra_msg=None):
        title = title or f'Task [{self.task_cls.__name__}] Error'
        if exc_info is not None:
            exc_msg = f'{format_exception(exc_info)}\n\n'
        else:
            exc_msg = ''
        extra_msg = extra_msg or ""
        msg = (f'<font color="warning">{title}</font>\n'
               f'{exc_msg}'
               f'{extra_msg}')
        return async_send_wx_markdown_message(msg)

    @safer(returns=None)
    def get_next_queue_url(self):
        url = config.MAGIC_WORKER_NEXT_QUEUE_URL
        if not url:
            return None
        resp = requests.post(
            url,
            json={
                'hostname': socket.gethostname(),
                'task_count': self.task_count,
                'boot_time': self.boot_time,
                'allow_task_types': self.allow_task_types,
            }
        )
        if resp.status_code != 200:
            self.logger.info(f'NEXT_URL: resp statu_code={resp.status_code}')
            return None
        payload = resp.json()
        if payload['code'] != 0:
            self.logger.info(f'NEXT_URL: resp code is not 0: {payload["code"]}')
            return None
        next_queue_url = payload.get('next_queue_url')
        if next_queue_url is not None:
            self.logger.info(f'Received next_queue_url: {next_queue_url}')
            # TODO: validate url
            return next_queue_url

        return None

    def safe_consume_message(self, message):
        task = self.task_cls.from_sqs_message(message)
        try:
            boot_time = time.time()
            if self.is_auto_task_report_start:
                task.mark_start()

            body = task.extract_param(message)
            task.process_task(body)

            end_time = time.time()
            elapsed_time = end_time - boot_time
            task.logger.info('elapsed_time={:.4f}'.format(elapsed_time))
            task.metric.time(metric_name='TASK_ELAPSED_TIME', value=elapsed_time * 1000)
            if self.is_auto_task_report_finish:
                task.mark_finish()
            self.task_count['success'] += 1
        except TaskError as e:
            # Dont retry TaskError
            if self.is_auto_task_report_error:
                task.mark_error(error_code=e.error_code)
            task.logger.error(f'Biz error: {e}, error_code: {e.error_code}')
            self.task_count['failed'] += 1
            self.report_error_to_wx(
                title=f'Task [{self.task_cls.__name__}] Biz Error',
                exc_info=sys.exc_info(),
                extra_msg=(f'HostName: {socket.gethostname()}\n'
                           f'Project ID: {task.project_id}\n'
                           f'Flow ID: {task.flow_id}\n'
                           f'Task ID: {task.task_id}')
            )
        except Exception as e:
            if self.is_auto_task_report_error:
                task.mark_error()
            task.logger.error(f'failed to process task, {str(e)}')
            self.task_count['error'] += 1
            self.report_error_to_wx(
                title=f'Task [{self.task_cls.__name__}] UNKNOWN Error',
                exc_info=sys.exc_info(),
                extra_msg=(f'HostName: {socket.gethostname()}\n'
                           f'Project ID: {task.project_id}\n'
                           f'Flow ID: {task.flow_id}\n'
                           f'Task ID: {task.task_id}')
            )
            raise e

    def _process_task(self, message, queue_url):
        try:
            self.safe_consume_message(message)
            self.sqs_client.delete_message(
                sqs_message=message,
                queue_url=queue_url,
            )
            return None
        except Exception as e:
            if self.is_delete_sqs_message_when_error:
                self.sqs_client.delete_message(
                    sqs_message=message,
                    queue_url=queue_url,
                )
            logging.exception(f'Unknown Error')
            return e

    def _on_interrupted(self, signum):
        config.stop_watches()
        self.logger.warning(f'Received interrupt signal: {signum}')
        sys.stdout.write(f'Received interrupt signal: {signum}\n')

    def _meltdown_enabled(self):
        return config.MAGIC_MELTDOWN_ENABLED == 'true'

    def loop_forever(self):
        self.boot_time = time.time()
        timeout = 5
        max_error_counts = 5
        with GracefulInterruptHandler(on_interrupt=self._on_interrupted) as h:
            error_count = 0
            while (not self._meltdown_enabled() or error_count < max_error_counts) and not self._has_trigger_stop():
                try:
                    queue_url = self.get_next_queue_url()
                    if queue_url is None:
                        queue_url = self.queue_url
                    else:
                        self.logger.info(f'Query next queue url: {queue_url}')

                    self.logger.info(f'loop fetching {self.task_concurrency} messages from {queue_url}, timeout: {timeout}s')
                    # NOTE: set `max_message_num` to be 1,
                    # in case later messages being executed after `Visibility timeout`
                    messages = self.sqs_client.fetch_messages(
                        max_message_num=self.task_concurrency,
                        queue_url=queue_url,
                        delete_on_fetch=False,
                        timeout=timeout,
                    )
                    message_count = len(messages)
                    if message_count > 0:
                        self.logger.info(f'Got {message_count} messages')
                    result = []
                    with ThreadPoolExecutor(max_workers=self.task_concurrency) as executor:
                        futures = [executor.submit(self._process_task, message, queue_url) for message in messages]
                        try:
                            for future in futures:
                                result.append(future.result())
                        except Exception as e:
                            logging.error(e)
                    error_count = 0
                    for e in result:
                        if e is not None:
                            error_count += 1
                except Exception:
                    error_count += 1
                    self.logger.exception(
                        f'Unknown error, error count: '
                        f'{error_count}/{max_error_counts}'
                    )

                if self._is_check_scheduled_terminate and self._is_scheduled_terminate():
                    self.logger.info(f'Spot Instance termination scheduled, stop worker')
                    break

                if self._has_trigger_stop():
                    self.logger.info(f'Triggered stop')
                    break

                if h.interrupted:
                    self.logger.info(f'User interrupted, stop gracefully')
                    sys.stdout.write(f'User interrupted, stop gracefully\n')
                    break

            if error_count >= max_error_counts:
                self.logger.error(f'Service Meltdown !!!')
                self.report_error_to_wx(
                    title=f'Service MELTDOWN!',
                    extra_msg=f'Hostname: {socket.gethostname()}'
                )
