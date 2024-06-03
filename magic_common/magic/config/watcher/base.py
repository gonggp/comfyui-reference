import threading
import time
import logging


logger = logging.getLogger()


class ConfigWatcherBase(object):

    def __init__(self, interval_secs=10):
        self.interval_secs = interval_secs
        self._thread = None
        self._last_update_time = None
        self._data = {}
        self._updater = None
        self._stop_watch = threading.Event()
        self.refresh()

    def start_watch(self):
        self._thread = threading.Thread(target=self.loop_refresh)
        self._thread.start()

    def stop_watch(self):
        self._stop_watch.set()

    def set_updater(self, updater):
        if callable(updater):
            self._updater = updater

    def use_effect(self):
        if self._updater:
            self._updater(self._data)

    def __del__(self):
        if self._thread:
            self.stop_watch()

    def loop_refresh(self):
        while not self._stop_watch.is_set():
            try:
                self.refresh()
                logger.debug('refresh config with '
                             f'{self.__class__.__name__}')
            except Exception:
                logger.exception('Failed to refresh config '
                                 f'from {self.__class__.__name__}')
            finally:
                time.sleep(self.interval_secs)

    def refresh(self):
        raise NotImplemented
