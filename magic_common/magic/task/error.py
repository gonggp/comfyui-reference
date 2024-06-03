class TaskError(Exception):

    def __init__(self, message, *args, **kwargs):
        self.error_code = kwargs.pop('error_code', None)
        super().__init__(message, *args)


class RetryableTaskError(Exception):
    pass
