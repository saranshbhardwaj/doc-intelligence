"""
Per-directory conftest for tests/unit/core/rag/.

Pre-imports real app modules so that test_rag_service_ambient.py's
_CatchallFinder (installed at collection time) cannot stub them out.
conftest.py runs before test module files are collected.
"""
import sys
from unittest.mock import MagicMock

# Stub heavy ML / optional packages that are not installed in the unit-test
# environment.  These stubs must be in place before the real app modules are
# imported below, or the imports will fail with ModuleNotFoundError.
for _mod in ("sentence_transformers", "tiktoken"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

# Force the real implementations into sys.modules now.  When
# test_rag_service_ambient.py is later collected it will install a
# _CatchallFinder, but the finder skips modules already present in
# sys.modules, so the real modules are preserved.
from app.core.rag import reranker as _reranker_mod   # noqa: F401
from app.core.rag import query_decomposer as _qd_mod  # noqa: F401
