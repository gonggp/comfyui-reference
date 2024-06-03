import os
import json

import boto3


class SecretManager(object):

    def __init__(self, secret_name, region=None):
        self.secret_name = secret_name
        self.region = region or os.environ.get('AWS_REGION', 'us-east-1')
        self.client = boto3.client("secretsmanager", region_name=self.region)
        self._last_change_date = None

    def get_all_values(self):
        resp = self.client.get_secret_value(SecretId=self.secret_name)
        return json.loads(resp['SecretString'])

    def get_last_update_time(self):
        resp = self.client.describe_secret(SecretId=self)
        return resp['LastChangeDate']

    def has_update(self):
        if self._last_change_date is None:
            return True
        last_time = self.get_last_update_time()
        return self._last_change_date < last_time
