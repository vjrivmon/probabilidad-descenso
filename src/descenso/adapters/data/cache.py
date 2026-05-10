"""Cache local en Parquet. Escritura atómica (tmp + replace) para no corromper en mitad."""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd


class ParquetCache:
    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = cache_dir

    def path(self, name: str) -> Path:
        return self.cache_dir / f"{name}.parquet"

    def has(self, name: str) -> bool:
        return self.path(name).exists()

    def load(self, name: str) -> pd.DataFrame:
        return pd.read_parquet(self.path(name))

    def save(self, name: str, df: pd.DataFrame) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        target = self.path(name)
        tmp = target.with_suffix(".parquet.tmp")
        df.to_parquet(tmp, index=False)
        os.replace(tmp, target)
