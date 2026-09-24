"""Trap planting and registration, one function per trap.

"plant_*" functions change the data on purpose: they add or alter rows so a
naive query gets a wrong answer. "register_*" functions change nothing; they
record facts about the world in the trap manifest so tests can assert on them.
"""
