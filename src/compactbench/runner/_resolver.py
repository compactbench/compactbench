"""Resolve ``--method`` CLI specs to Compactor classes."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from compactbench.compactors import Compactor, get_built_in
from compactbench.compactors.errors import UnknownCompactorError
from compactbench.runner.errors import MethodResolutionError


def resolve_compactor_class(spec: str) -> type[Compactor]:
    """Resolve a ``--method`` spec to a :class:`Compactor` class.

    Two spec forms are supported:

    - ``built-in:<key>`` — look up in the built-in registry.
    - ``<path>:<ClassName>`` — load ``ClassName`` from the Python file at ``<path>``.
      The class must subclass :class:`Compactor`.
    """
    if spec.startswith("built-in:"):
        key = spec[len("built-in:") :]
        try:
            return get_built_in(key)
        except UnknownCompactorError as exc:
            raise MethodResolutionError(str(exc)) from exc

    if ":" not in spec:
        raise MethodResolutionError(
            f"could not resolve method {spec!r}. Use 'built-in:<key>' or '<path>:<ClassName>'."
        )

    path_str, class_name = spec.rsplit(":", 1)
    path = Path(path_str)
    if not path.is_file():
        raise MethodResolutionError(f"method file not found: {path}")
    if path.suffix != ".py":
        raise MethodResolutionError(f"method file must be a .py file: {path}")

    module_spec = importlib.util.spec_from_file_location(f"_user_compactor_{path.stem}", path)
    if module_spec is None or module_spec.loader is None:
        raise MethodResolutionError(f"could not load module from {path}")
    module = importlib.util.module_from_spec(module_spec)
    sys.modules[module_spec.name] = module
    try:
        module_spec.loader.exec_module(module)
    except Exception as exc:
        raise MethodResolutionError(f"error importing {path}: {exc}") from exc

    cls = getattr(module, class_name, None)
    if cls is None:
        raise MethodResolutionError(f"class {class_name!r} not found in {path}")
    if not isinstance(cls, type) or not issubclass(cls, Compactor):
        raise MethodResolutionError(f"{class_name!r} in {path} is not a subclass of Compactor")
    return cls
