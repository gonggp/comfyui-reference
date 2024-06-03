import io
import os
import logging
import threading
import sys

import boto3
from botocore.exceptions import ClientError

from magic.config import config


logger = logging.getLogger()


class ProgressPercentage(object):
    def __init__(self, client=None, bucket=None, key=None, size=None):
        self._size = (
            size or client.head_object(Bucket=bucket, Key=key)["ContentLength"]
        )
        self._seen_so_far = 0
        self._lock = threading.Lock()
        self.prog_bar_len = 80

    def __call__(self, bytes_amount):
        with self._lock:
            self._seen_so_far += bytes_amount
            ratio = round(
                (float(self._seen_so_far) / float(self._size))
                * (self.prog_bar_len - 6),
                1,
            )  # noqa
            current_length = int(round(ratio))

            percentage = round(100 * ratio / (self.prog_bar_len - 6), 1)

            bars = "+" * current_length
            output = (
                bars
                + " " * (self.prog_bar_len - current_length - len(str(percentage)) - 1)
                + str(percentage)
                + "%"
            )  # noqa

            if self._seen_so_far != self._size:
                sys.stdout.write(output + "\r")
            else:
                sys.stdout.write(output + "\n")
            sys.stdout.flush()


class S3FileManager(object):

    DEFAULT_EXPIRATION = 60 * 60

    def __init__(self, region=None, default_bucket=None):
        self.region = region or config.AWS_REGION
        self.default_bucket = default_bucket or config.AWS_DEFAULT_BUCKET
        self.client = boto3.client("s3", region_name=self.region)

    def _download_file(self, bucket, file_key, local_filepath):
        try:
            bucket = bucket or self.default_bucket
            pp = ProgressPercentage(
                client=self.client,
                bucket=bucket,
                key=file_key
            )
            return self.client.download_file(
                bucket, file_key, local_filepath, Callback=pp)
        except ClientError as e:
            logger.exception(f'failed to download file')
            raise e

    def get_public_url(self, file_key, bucket=None, region=None):
        region = region or self.region
        bucket = bucket or self.default_bucket
        return f'https://{bucket}.s3.{region}.amazonaws.com/{file_key}'

    def presign_download_url(self, file_key: str, bucket: str = None, expires_in: int = DEFAULT_EXPIRATION) -> str:
        try:
            bucket = bucket or self.default_bucket
            return self.client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": bucket,
                    "Key": file_key,
                },
                ExpiresIn=expires_in,
            )
        except ClientError as e:
            logger.exception('failed to presign download url '
                             f'for s3://{bucket}/{file_key}')
            raise e

    def download_to_file(self, file_key, local_filepath, bucket=None):
        try:
            bucket = bucket or self.default_bucket
            self.client.head_object(Bucket=bucket, Key=file_key)
            self._download_file(bucket, file_key, local_filepath)
            return local_filepath
        except ClientError as e:
            logger.exception(f'failed to download to file: s3://{bucket}/{file_key}')
            raise e

    def upload_from_file(self, local_filepath, file_key, content_type=None, bucket=None):
        if content_type:
            extra_args = {'ContentType': content_type}
        else:
            extra_args = {}
        pp = ProgressPercentage(size=os.stat(local_filepath).st_size)
        try:
            bucket = bucket or self.default_bucket
            self.client.upload_file(
                local_filepath,
                bucket,
                file_key,
                Callback=pp,
                ExtraArgs=extra_args,
            )
        except ClientError as e:
            logger.exception(f'failed to upload from file: s3://{bucket}/{file_key}')
            raise e

    def download_obj(self, file_key, bucket=None):
        try:
            buff = io.BytesIO()
            bucket = bucket or self.default_bucket
            self.client.download_fileobj(bucket, file_key, buff)
            buff.seek(0)
            return buff
        except ClientError as e:
            logger.exception(f'failed to download obj from s3://{bucket}/{file_key}')
            raise e

    def upload_obj(self, file_obj, file_key, content_type=None, bucket=None):
        if content_type:
            extra_args = {'ContentType': content_type}
        else:
            extra_args = {}

        try:
            bucket = bucket or self.default_bucket
            self.client.upload_fileobj(file_obj, bucket, file_key, ExtraArgs=extra_args)
        except ClientError as e:
            logger.exception(f'failed to upload obj to s3://{bucket}/{file_key}')
            raise e

    def upload_text(self, text: str, file_key: str, content_type=None, bucket=None):
        buff = io.BytesIO()
        buff.write(text.encode())
        buff.seek(0)
        return self.upload_obj(buff, file_key, content_type, bucket)

    def download_text(self, file_key: str, bucket=None):
        buff = self.download_obj(file_key, bucket=bucket)
        buff.seek(0)
        return buff.read()

    def head_object(self, file_key, bucket=None):
        bucket = bucket or self.default_bucket
        return self.client.head_object(Bucket=bucket, Key=file_key)

    def is_object_exist(self, file_key, bucket=None):
        bucket = bucket or self.default_bucket
        try:
            return bool(self.head_object(file_key, bucket=bucket))
        except ClientError:
            return False


default_s3_client = S3FileManager(
    region=config.AWS_REGION,
    default_bucket=config.AWS_DEFAULT_BUCKET
)
