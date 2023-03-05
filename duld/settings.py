import sys

import yaml


class Settings(object):
    def __init__(self):
        self._data = None

    def __getitem__(self, key):
        return self._data[key]

    def reload(self, path):
        with open(path, mode="r", encoding="utf-8") as fin:
            self._data = yaml.safe_load(fin)


sys.modules[__name__] = Settings()
