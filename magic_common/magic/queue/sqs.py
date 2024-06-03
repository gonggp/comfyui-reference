import logging

import boto3

from magic.utils.json import safe_load_json


logger = logging.getLogger()


class SQSClient(object):

    def __init__(self, region, queue_url=None):
        self.client = boto3.client("sqs", region_name=region)
        self.queue_url = queue_url

    def fetch_messages(self, max_message_num=1, queue_url=None, delete_on_fetch=False, timeout=10):
        queue_url = queue_url or self.queue_url

        resp = self.client.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=max_message_num,
            WaitTimeSeconds=timeout,
            AttributeNames=["All"],
        )
        messages = resp.get('Messages', [])
        if delete_on_fetch:
            for msg in messages:
                self.delete_message(msg, queue_url)
        return messages

    def put_message(self, queue_url, body, delay=None, message_group_id=None, message_deduplication_id=None):
        params = {
            'QueueUrl': queue_url,
            'MessageBody': body,
        }
        if message_group_id is not None:
            params['MessageGroupId'] = message_group_id
        if message_deduplication_id is not None:
            params['MessageDeduplicationId'] = message_deduplication_id
        if delay is not None:
            params['DelaySeconds'] = delay
        resp = self.client.send_message(**params)
        return resp

    def delete_message(self, sqs_message, queue_url=None):
        return self.client.delete_message(
            QueueUrl=queue_url,
            ReceiptHandle=sqs_message.get('ReceiptHandle'),
        )
