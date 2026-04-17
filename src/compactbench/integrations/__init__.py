"""Framework adapters for running CompactBench against other ecosystems.

Each submodule pulls its framework's SDK as an optional dependency; importing
a submodule without the SDK installed raises a clean :class:`ImportError` with
the ``pip install`` invocation that fixes it.
"""
