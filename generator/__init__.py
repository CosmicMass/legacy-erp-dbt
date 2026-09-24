"""Synthetic data generator for the legacy-erp-dbt project.

Run it with ``python -m generator``. It builds a clean world first, then plants
the traps T1-T16 on purpose, checks every planted count, and writes the raw
seed CSVs plus the trap manifest to ``seeds/``.
"""
