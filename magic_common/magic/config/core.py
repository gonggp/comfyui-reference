import os

from magic.config.watcher.base import ConfigWatcherBase


class Config(object):

    def __init__(self):
        self._vars = {}
        self._not_empty = set()
        self._watchers = set()

    def add_watcher(self, watcher: ConfigWatcherBase):
        self._watchers.add(watcher)
        watcher.set_updater(self.update_config)
        watcher.start_watch()

    def update_config(self, updates=None):
        if updates:
            self._vars.update(updates)

    def stop_watches(self):
        for watcher in self._watchers:
            watcher.stop_watch()

    def register(self, key, default=None, not_empty=False):
        self._vars[key] = default
        if not_empty:
            self._not_empty.add(key)

    def reload_from_envs(self):
        for k in self._vars.keys():
            self._vars[k] = os.environ.get(k)

    def check_not_empty(self):
        for k, v in self._vars.items():
            if k in self._not_empty and (v is None or not v):
                raise ValueError(f'Config `{k}` is empty')

    def __getattr__(self, key):
        if key in self._vars:
            return self._vars[key]

        # fallback to os.environ
        val = os.environ.get(key, None)
        if val is not None:
            return val

        raise AttributeError(f'Config `{key}` not found')
