import tomllib
from pathlib import Path


class Config:
    __instance = None

    def __new__(cls):
        if cls.__instance is None:
            cls.__instance = super().__new__(cls)
        return cls.__instance

    def __init__(self):
        with open(Path('data', 'config.toml'), 'rb') as f:
            self.data = tomllib.load(f)

    @property
    def groups(self) -> list[str]:
        return self.data['groups']

    @property
    def fetch_new_count(self) -> int:
        return self.data['fetch_new_count']

    @property
    def fetch_count(self) -> int:
        return self.data['fetch_count']

    @property
    def fetch_interval_minutes(self) -> int:
        return self.data['fetch_interval_minutes']
