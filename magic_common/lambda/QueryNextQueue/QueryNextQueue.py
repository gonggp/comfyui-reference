import json
import logging

import boto3


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()
sqs = boto3.client('sqs')


SMALL_SIZE_QUEUE_URL = "https://sqs.us-east-1.amazonaws.com/647854334008/DiffuserServer-Input-SmallSizeDeque"


def get_queue_length(queue_url):
    resp = sqs.get_queue_attributes(
        QueueUrl=queue_url,
        AttributeNames=[
            'ApproximateNumberOfMessages',
        ]
    )
    try:
        return int(resp['Attributes']['ApproximateNumberOfMessages'])
    except Exception:
        logger.exception(f'Failed to get queue length for {queue_url}')
        return 0


def get_queue_url(hostname, task_count, boot_time, allow_task_types):
    if 'diffuser' in allow_task_types:
        queue_length = get_queue_length(SMALL_SIZE_QUEUE_URL)
        if queue_length > 0:
            return SMALL_SIZE_QUEUE_URL
    return None


def lambda_handler(event, context):
    body = json.loads(event['body'])
    hostname = body.get('hostname')
    task_count = body.get('task_count', {})
    boot_time = body.get('boot_time', None)
    allow_task_types = body.get('allow_task_types', [])

    print(f'Hostname: {hostname}, '
          f'task_count: {task_count}, '
          f'boot_time: {boot_time}, '
          f'Allow TaskTypes: {allow_task_types}')

    next_queue_url = get_queue_url(hostname, task_count, boot_time, allow_task_types)
    response = {
        'code': 0,
        'next_queue_url': next_queue_url,
    }

    return {
        'statusCode': 200,
        'body': json.dumps(response)
    }
