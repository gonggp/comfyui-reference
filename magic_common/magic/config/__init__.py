from magic.config.core import Config    # noqa


config = Config()

# AWS Configuration
config.register('AWS_REGION', 'us-east-1')
config.register('AWS_DEFAULT_BUCKET', '')
config.register('AWS_SQS_QUEUE_URL', '')

# Magic Common
config.register('MAGIC_LOG_LEVEL', 'INFO')
config.register('MAGIC_LOG_PATH', '/var/log/magic_service')
config.register('MAGIC_TASK_REPORT_API_BASE', '')
config.register('MAGIC_TASK_CLASS_NAME', '')
config.register('MAGIC_WORKER_NEXT_QUEUE_URL', '')
config.register('MAGIC_MELTDOWN_ENABLED', 'true')
config.register('MAGIC_WX_ERROR_URL', '')

reload_envs = config.reload_from_envs
