"""Import `query_translation.*` submodules WITHOUT running the package __init__.

The real `query_translation/__init__.py` imports `views`, which pulls in Flask /
the whole app. The OQL conformance harness only needs the pure data-model +
translation modules (`oqo`, `oqo_canonicalizer`, `oql_parser`, `oql_renderer`).

We register a stub `query_translation` package in `sys.modules` (with the right
`__path__`) *before* any import, so Python's import machinery treats the package
as already-initialized and never executes the real `__init__.py`. Submodule
imports (`from query_translation.oqo import ...`) then resolve against the stub's
`__path__` and load the individual .py files normally.
"""
import os
import sys
import types

_QT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "query_translation",
)


def install_stub_package():
    if "query_translation" not in sys.modules:
        pkg = types.ModuleType("query_translation")
        pkg.__path__ = [_QT_DIR]  # marks it a package; submodules load from here
        pkg.__package__ = "query_translation"
        sys.modules["query_translation"] = pkg


install_stub_package()
