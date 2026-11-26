"""Every gimera module must import on the platform the tests run on.

A platform-only import once made gimera crash on Linux right at start-up
(``from ctypes.wintypes import ...``, which raises on Linux up to Python 3.7).
On the supported versions that import works, but other Windows-only modules
such as ``winreg`` or ``msvcrt`` still fail. Most modules are imported by
other tests anyway, but this test walks the whole package so that a module no
test touches cannot hide such an import.
"""
import importlib
import pkgutil

import pytest

import gimera

MODULES = sorted(
    name
    for _finder, name, _ispkg in pkgutil.walk_packages(
        gimera.__path__, prefix="gimera."
    )
    if not name.startswith("gimera.tests")
)


def test_modules_found():
    assert "gimera.gimera" in MODULES


@pytest.mark.parametrize("module", MODULES)
def test_module_imports(module):
    importlib.import_module(module)
