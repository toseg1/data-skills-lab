"""Dataset generation and materialisation for the Data Skills Lab."""

from __future__ import annotations

from lab.data.generate import Dataset, GeneratorConfig, generate_dataset, stream_rng
from lab.data.writers import write_all, write_duckdb, write_parquet, write_raw_files

__all__ = [
    "Dataset",
    "GeneratorConfig",
    "generate_dataset",
    "stream_rng",
    "write_all",
    "write_duckdb",
    "write_parquet",
    "write_raw_files",
]
