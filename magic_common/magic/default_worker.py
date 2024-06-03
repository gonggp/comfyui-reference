import logging

from magic.config import config
from magic.task.base import TaskBase
from magic.task.worker import Worker


logger = logging.getLogger()
TASK_CLS = TaskBase
QUEUE_URL = None


def main():
    task_cls = TASK_CLS
    if task_cls is None or task_cls == TaskBase:
        task_cls = __import__(config.TASK_CLASS_NAME)
    if task_cls is None:
        raise RuntimeError('Task class not defined')

    queue_url = QUEUE_URL
    if queue_url is None:
        queue_url = config.AWS_SQS_QUEUE_URL

    worker = Worker(task_cls, queue_url)
    logger.info(f'Worker started, listening {queue_url}')
    worker.loop_forever()


if __name__ == "__main__":
    main()
