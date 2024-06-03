import time
import logging

from magic.aws.secretmanager import SecretManager
from magic.config.watcher.base import ConfigWatcherBase

logger = logging.getLogger()


class SecretManagerConfigWatcher(ConfigWatcherBase):

    def __init__(self, secret_name, interval_secs=10):
        self.secret_name = secret_name
        self._client = SecretManager(self.secret_name)
        super().__init__(interval_secs)

    def refresh(self):
        if not self._client.has_update():
            return

        to_updates = self._client.get_all_values()
        if to_updates:
            self._data.update(to_updates)
            self._last_update_time = time.time()
            self.use_effect()
        return self._data

    def loop_refresh(self):
        while not self._stop_watch.is_set():
            try:
                self.refresh()
                logger.debug(f'Refresh config from {self.secret_name}')
            except Exception:
                logger.exception('Failed to refresh config '
                                 f'from {self.__class__.__name__}, '
                                 f'{self.secret_name}')
            finally:
                time.sleep(self.interval_secs)
