Magic Common
============

Common library for Magic Services.

# Guidance

## 1. Add `magic` in your project

Include `magic` in your project by:

1. Clone to repository by `git submodule`
2. Install python by `pip install git+https://github.com/MagiclightGit/magic_common.git`

## 2. Implement Task Class

Extend class `magic.task.base.TaskBase` and implement following methods:

1. `def extract_param(self, sqs_message)`: Extract `Body` and other params from SQS message.
2. `def process_task(self, params)`: Run the model without handle task reporting and queue message.
3. use `self.logger` to auto inject meta information in logs, project_id, flow_id and so on.

Example:

```python
import os
import json
import tempfile
import logging

from magic.task.base import TaskBase
from magic.storage.s3 import default_s3_client as s3_client
from magic.utils.fuzzy_download import fuzzy_download_to_file

from whatever import DiffusersModel, make_watermark


logger = logging.getLogger('magic.worker')


class DiffusersSDXLTask(TaskBase):
    
    TASK_TYPE = 'generation_subtask'

    def extract_param(self, sqs_msg):
        """
        Extract Body from SQS Message.
        Do nothing and return directly.
        """
        body = json.loads(sqs_msg.get('Body', ''))
        return body
    
    def process_task(self, body):
        params = body.get('params', '')
        # Init body with params
        self._init_with_params(params)
        
        # Inference
        output_image_path = self.model(self.image_path)
        
        # post process
        watermark_path = self._watermark(output_image_path)
        
        # upload result
        file_key = f'diffusers-outputs/{self.project_id}_{self.flow_id}_{self.task_id}.jpg'
        s3_client.upload_from_file(output_image_path, file_key, content_type='image/jpeg')
        
        file_key = f'diffusers-outputs/{self.project_id}_{self.flow_id}_{self.task_id}_wm.jpg'
        s3_client.upload_from_file(watermark_path, file_key, content_type='image/jpeg')
    
    def _download_file(self, model_url):
        filename = os.path.basename(model_url)
        if '.' in filename:
            _, extension = os.path.splitext(filename)
            tmp_file = tempfile.NamedTemporaryFile(suffix=f'.{extension}')
        else:
            tmp_file = tempfile.NamedTemporaryFile()
        local_filepath = tmp_file.name
        
        return fuzzy_download_to_file(model_url, local_filepath)

    def _init_with_params(self, params):
        self.logger.info(f'init with params: {params}')
        input_data = params.get('input_data', {})
        model_url = input_data['model_url']
        image_url = input_data['image_url']
        self.model_path = self.download_file(model_url)
        self.logger.info(f'downloaded model from {model_url} to {self.model_path}')
        self.image_path = self.download_file(image_url)
        self.logger.info(f'downloaded image from {image_url} to {self.image_path}')
        self.model = DiffusersModel(model=self.model_path)

    def _watermark(self, image_path):
        return make_watermark(image_path)
```

## 3. Start with worker.py

### Start worker in default way

Add `worker.py` in your project:

```python
from magic import default_worker

if __name__ == '__main__':
    default_worker.main()
```

Start your worker:

```bash
$ export AWS_REGION="us-east-1"
$ export AWS_DEFAULT_BUCKET="aigc-outputs"
$ export AWS_SQS_QUEUE_URL="https://sqs.us-east-1.amazonaws.com/647854334008/AidenTest"
$ export TASK_CLASS_NAME="your_project.modules.task.DiffusersSDXLTask"  # set to be Task python name
$ python worker.py
```

### Start worker with advanced way

Add `worker.py` in your project:

```python
import logging

from magic.task.worker import Worker
from magic.storage.s3 import default_s3_client as s3_client

from your_project.modules.task import DiffusersSDXLTask


logger = logging.getLogger()


def main():
    aws_region = 'us-east-1'
    sqs_queue_url = "https://sqs.us-east-1.amazonaws.com/647854334008/AidenTest"
    task_cls = DiffusersSDXLTask
    s3_client.region = aws_region
    s3_client.default_bucket = "agic-outputs"
    worker = Worker(task_cls, sqs_queue_url, region=aws_region)
    logger.info(f'Worker started, listening {sqs_queue_url}')
    worker.loop_forever()


if __name__ == '__main__':
    main()
```

And start your worker:

```bash
$ python worker.py
```

## Config

```python
from magic.config import config
from magic.config.watcher.secretmanager import SecretManagerConfigWatcher


"""
IpBibleConfig:

{
    "IpBible_CacheEnabled": "yes",
}
"""

def init():
    config_watcher = SecretManagerConfigWatcher("IpBibleConfig", interval_secs=10)
    config.add_watcher(config_watcher)


def run_single_task():
    if config.IpBible_CacheEnabled == "yes":
        return get_from_cache()
    else:
        pass
```


## WX Exception Report

```bash
export MAGIC_WX_ERROR_URL="https://..."
```
