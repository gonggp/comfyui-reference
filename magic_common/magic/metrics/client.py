import time
from functools import wraps

import boto3

from magic.utils.wrapper import safer


class MetricClient(object):

    def __init__(self, region, namespace, task_type):
        self.client = boto3.client('cloudwatch', region_name=region)
        self.namespace = namespace
        self.task_type = task_type
        self.dimensions = [
            {
                'Name': 'TaskType',
                'Value': str(self.task_type),
            }
        ]

    @safer()
    def time(self, metric_name, value, unit='Milliseconds'):
        self.client.put_metric_data(
            Namespace=self.namespace,
            MetricData=[
                {
                    'Dimensions': self.dimensions,
                    'MetricName': metric_name,
                    'Value': value,
                    'Unit': unit,
                }
            ]
        )

    @safer()
    def count(self, metric_name, value=1, unit='Count'):
        self.client.put_metric_data(
            Namespace=self.namespace,
            MetricData=[
                {
                    'Dimensions': self.dimensions,
                    'MetricName': metric_name,
                    'Value': value,
                    'Unit': unit,
                }
            ]
        )

    @safer()
    def gauge(self, metric_name, value, unit=''):
        self.client.put_metric_data(
            Namespace=self.namespace,
            MetricData=[
                {
                    'Dimensions': self.dimensions,
                    'MetricName': metric_name,
                    'Value': value,
                    'Unit': unit,
                }
            ]
        )

    def timer(self, metric_name):
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                start = time.time()
                ret = func(*args, **kwargs)
                end = time.time()
                self.time(metric_name, (end - start) * 1000)
                return ret
            return wrapper
        return decorator
