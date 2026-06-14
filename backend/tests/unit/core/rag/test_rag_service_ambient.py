"""Tests for ambient routing in RAGService.

Verifies that when scope_mode == AMBIGUOUS and multiple documents are in session:
 - filter_noise() is called instead of rerank()
 - build_ambient_split() is called instead of build_split()

Also verifies that when scope_mode == AMBIGUOUS but only one document is in
session, the existing (non-ambient) behavior is preserved.

Heavy dependencies (pgvector, sqlalchemy ORM models, etc.) are stubbed via
sys.modules before importing rag_service so the module loads cleanly in the
unit-test environment.
"""
import sys
import types
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Stub heavy C-extension / database modules before importing rag_service.
# This mirrors how other unit tests in this project deal with optional deps.
# ---------------------------------------------------------------------------

def _stub_module(name: str, **attrs) -> types.ModuleType:
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


def _ensure_stubs():
    """Install module stubs if the real packages are not available."""
    if "pgvector" not in sys.modules:
        _stub_module("pgvector")
        pgsql = _stub_module("pgvector.sqlalchemy")
        pgsql.Vector = MagicMock  # Vector(768) column type stub

    # Stub sqlalchemy so db_models_chat can be imported
    if "sqlalchemy" not in sys.modules:
        sa = _stub_module("sqlalchemy")
        sa_orm = _stub_module("sqlalchemy.orm")
        sa_orm.Session = MagicMock
        sa_orm.relationship = MagicMock()
        sa_orm.mapped_column = MagicMock()
        sa_orm.Mapped = MagicMock
        sa_ext = _stub_module("sqlalchemy.ext")
        sa_ext_dec = _stub_module("sqlalchemy.ext.declarative")
        sa_ext_dec.declarative_base = lambda: MagicMock()
        sa.Column = MagicMock
        sa.String = MagicMock
        sa.Integer = MagicMock
        sa.Boolean = MagicMock
        sa.Text = MagicMock
        sa.DateTime = MagicMock
        sa.ForeignKey = MagicMock
        sa.select = MagicMock
        sa.func = MagicMock()

    # Stub prometheus_client to prevent registry conflicts
    if "prometheus_client" not in sys.modules:
        pc = _stub_module("prometheus_client")
        pc.Histogram = MagicMock
        pc.Counter = MagicMock
        pc.Gauge = MagicMock
        pc.Summary = MagicMock
        pc.start_http_server = MagicMock()


_ensure_stubs()


import importlib
import importlib.abc
import importlib.machinery


class _CatchallModule(types.ModuleType):
    """A module stub where any attribute access returns a fresh MagicMock."""

    def __init__(self, name: str):
        super().__init__(name)
        # Mark as a package so submodule imports work
        self.__path__ = []
        self.__package__ = name
        self.__spec__ = importlib.machinery.ModuleSpec(name, None, is_package=True)

    def __getattr__(self, name: str):
        value = MagicMock()
        setattr(self, name, value)
        return value


class _CatchallFinder(importlib.abc.MetaPathFinder):
    """
    A meta path finder that intercepts imports of specified package prefixes
    and returns a _CatchallModule stub instead of the real module.

    This covers both `import foo.bar` and `from foo.bar import Baz` patterns
    without requiring us to enumerate every submodule upfront.
    """

    def __init__(self, prefixes: tuple):
        self._prefixes = prefixes

    def find_spec(self, fullname, path, target=None):
        if any(fullname == p or fullname.startswith(p + ".") for p in self._prefixes):
            if fullname not in sys.modules:
                sys.modules[fullname] = _CatchallModule(fullname)
            spec = sys.modules[fullname].__spec__
            if spec is None:
                spec = importlib.machinery.ModuleSpec(fullname, None, is_package=True)
                sys.modules[fullname].__spec__ = spec
            return spec
        return None


def _ensure_app_model_stubs():
    """
    Stub ORM model modules, repository packages, and optional C-extensions that
    rag_service.py's import chain requires but are not available in the unit-test
    environment (no pgvector, no openai SDK, no sentence-transformers, etc.).

    Strategy: install a _CatchallFinder at the front of sys.meta_path that
    intercepts any import whose name starts with one of our stub prefixes and
    returns a MagicMock-backed module.  This avoids having to enumerate every
    submodule upfront.

    Stubs are idempotent — subsequent calls are no-ops.
    """
    _stub_prefixes = (
        # ORM model files (pgvector not installed in unit-test env)
        "app.db_models_chat",
        "app.db_models_users",
        "app.db_models_documents",
        "app.db_models_workflows",
        "app.db_models_templates",
        "app.db_models_feedback",
        "app.db_models",
        # Repository package (imports all db_models at __init__ time)
        "app.repositories",
        # Service locator (imports reranker etc.)
        "app.services.service_locator",
        # Embedding submodules (openai not installed in unit-test env)
        "app.core.embeddings",
        # RAG collaborator modules (stubbed so rag_service.py can import)
        "app.core.rag.prompt_builder",
        "app.core.rag.memory",
        "app.core.rag.budget_enforcer",
        "app.core.rag.hybrid_retriever",
        "app.core.rag.reranker",
        "app.core.rag.comparison_retriever",
        "app.core.rag.comparison_flow",
        "app.core.rag.query_understanding",
        "app.core.rag.fact_extractor",
        "app.core.rag.context_expander",
        "app.core.rag.chat_persistence",
        "app.core.rag.document_matching",
        "app.core.rag.query_decomposer",
        "app.core.rag.low_signal",
        "app.core.rag.eval_contract",
        "app.core.rag.workflow_retriever",
        # LLM / embedding clients
        "app.core.llm",
        "app.core.chat",
        # LLM / metrics utils
        "app.utils.metrics",
        "app.utils.chunk_metadata",
        # Third-party optional packages not installed in unit-test env
        "sentence_transformers",
        "torch",
        "transformers",
        "openai",
        "anthropic",
        "tiktoken",
        "prometheus_client",
    )

    # Check if our finder is already installed
    for finder in sys.meta_path:
        if isinstance(finder, _CatchallFinder):
            return  # already installed

    # Pre-populate sys.modules for prefixes that may already be partially loaded
    for prefix in _stub_prefixes:
        if prefix not in sys.modules:
            sys.modules[prefix] = _CatchallModule(prefix)

    # Install the finder at the *front* so it takes priority
    sys.meta_path.insert(0, _CatchallFinder(_stub_prefixes))


_ensure_app_model_stubs()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_chunk(doc_id: str = "doc1", text: str = "some text") -> dict:
    return {
        "id": f"{doc_id}-chunk-1",
        "document_id": doc_id,
        "text": text,
        "page_number": 1,
        "chunk_index": 0,
        "hybrid_score": 0.5,
        "rerank_score": 0.5,
        "is_tabular": False,
        "section_heading": None,
        "section_type": "narrative",
        "chunk_metadata": {},
        "tables": None,
        "bbox": None,
        "page_range": None,
    }


# ---------------------------------------------------------------------------
# Core logic tests (white-box, no RAGService instantiation)
# ---------------------------------------------------------------------------

class TestIsAmbientCondition:
    """Verify the is_ambient flag logic matches the spec."""

    def test_ambiguous_multi_doc_is_ambient(self):
        """AMBIGUOUS + >1 doc → is_ambient True."""
        scope_mode = "AMBIGUOUS"
        document_ids = ["doc1", "doc2"]
        is_ambient = (
            scope_mode == "AMBIGUOUS"
            and bool(document_ids)
            and len(document_ids) > 1
        )
        assert is_ambient is True

    def test_ambiguous_single_doc_not_ambient(self):
        """AMBIGUOUS + 1 doc → is_ambient False."""
        scope_mode = "AMBIGUOUS"
        document_ids = ["doc1"]
        is_ambient = (
            scope_mode == "AMBIGUOUS"
            and bool(document_ids)
            and len(document_ids) > 1
        )
        assert is_ambient is False

    def test_single_doc_scope_not_ambient(self):
        """SINGLE_DOC scope → is_ambient False even with multiple session docs."""
        scope_mode = "SINGLE_DOC"
        document_ids = ["doc1", "doc2", "doc3"]
        is_ambient = (
            scope_mode == "AMBIGUOUS"
            and bool(document_ids)
            and len(document_ids) > 1
        )
        assert is_ambient is False

    def test_no_documents_not_ambient(self):
        """AMBIGUOUS + empty doc list → is_ambient False."""
        scope_mode = "AMBIGUOUS"
        document_ids = []
        is_ambient = (
            scope_mode == "AMBIGUOUS"
            and bool(document_ids)
            and len(document_ids) > 1
        )
        assert is_ambient is False


# ---------------------------------------------------------------------------
# Reranker routing tests (unit, mocked reranker)
# ---------------------------------------------------------------------------

class TestAmbientRerankerRouting:
    """Verify that ambient mode calls filter_noise, standard mode calls rerank."""

    def _make_reranker(self):
        r = MagicMock()
        r.rerank.return_value = [_make_chunk("doc1")]
        r.filter_noise.return_value = [_make_chunk("doc1"), _make_chunk("doc2")]
        return r

    def _route_rerank(self, is_ambient, reranker, chunks, retrieval_query, settings):
        """Replicate the ambient rerank routing logic from rag_service."""
        import functools
        if is_ambient and reranker and chunks:
            return reranker.filter_noise(
                query=retrieval_query,
                chunks=chunks,
                threshold=settings.rag_reranker_ambient_noise_threshold,
            )
        elif reranker and chunks:
            return reranker.rerank(
                query=retrieval_query,
                chunks=chunks,
            )
        else:
            return chunks

    def test_ambient_calls_filter_noise(self):
        """filter_noise() is used for ambient mode."""
        reranker = self._make_reranker()
        settings = MagicMock()
        settings.rag_reranker_ambient_noise_threshold = 0.05
        chunks = [_make_chunk("doc1"), _make_chunk("doc2")]

        result = self._route_rerank(
            is_ambient=True,
            reranker=reranker,
            chunks=chunks,
            retrieval_query="test query",
            settings=settings,
        )

        reranker.filter_noise.assert_called_once_with(
            query="test query",
            chunks=chunks,
            threshold=0.05,
        )
        reranker.rerank.assert_not_called()
        assert len(result) == 2

    def test_standard_calls_rerank(self):
        """rerank() is used for standard (non-ambient) mode."""
        reranker = self._make_reranker()
        settings = MagicMock()
        settings.rag_reranker_ambient_noise_threshold = 0.05
        chunks = [_make_chunk("doc1")]

        self._route_rerank(
            is_ambient=False,
            reranker=reranker,
            chunks=chunks,
            retrieval_query="test query",
            settings=settings,
        )

        reranker.rerank.assert_called_once()
        reranker.filter_noise.assert_not_called()

    def test_ambient_single_doc_calls_rerank(self):
        """When is_ambient is False (single doc), rerank is used."""
        reranker = self._make_reranker()
        settings = MagicMock()
        settings.rag_reranker_ambient_noise_threshold = 0.05
        chunks = [_make_chunk("doc1")]

        self._route_rerank(
            is_ambient=False,  # single doc → not ambient
            reranker=reranker,
            chunks=chunks,
            retrieval_query="test query",
            settings=settings,
        )

        reranker.rerank.assert_called_once()
        reranker.filter_noise.assert_not_called()


# ---------------------------------------------------------------------------
# Prompt builder routing tests (unit, mocked prompt_builder)
# ---------------------------------------------------------------------------

class TestAmbientPromptBuilderRouting:
    """Verify that ambient mode calls build_ambient_split, standard calls build_split."""

    def _make_prompt_builder(self):
        pb = MagicMock()
        pb.build_split.return_value = ("sys", "usr")
        pb.build_ambient_split.return_value = ("sys_ambient", "usr_ambient")
        return pb

    def _route_prompt(self, is_ambient, prompt_builder, chunks, user_message, recent_messages, summary_text, include_history):
        """Replicate the ambient prompt routing logic from rag_service."""
        if is_ambient:
            return prompt_builder.build_ambient_split(
                user_message=user_message,
                relevant_chunks=chunks,
                recent_messages=recent_messages,
                summary_text=summary_text,
                doc_id_to_index=None,
                include_history=include_history,
            )
        else:
            return prompt_builder.build_split(
                user_message=user_message,
                relevant_chunks=chunks,
                recent_messages=recent_messages,
                summary_text=summary_text,
                include_history=include_history,
            )

    def test_ambient_calls_build_ambient_split(self):
        """build_ambient_split() is used for ambient mode."""
        pb = self._make_prompt_builder()
        chunks = [_make_chunk("doc1"), _make_chunk("doc2")]

        result = self._route_prompt(
            is_ambient=True,
            prompt_builder=pb,
            chunks=chunks,
            user_message="what is the NOI?",
            recent_messages=[],
            summary_text=None,
            include_history=True,
        )

        pb.build_ambient_split.assert_called_once()
        pb.build_split.assert_not_called()
        assert result == ("sys_ambient", "usr_ambient")

    def test_standard_calls_build_split(self):
        """build_split() is used for standard (non-ambient) mode."""
        pb = self._make_prompt_builder()
        chunks = [_make_chunk("doc1")]

        self._route_prompt(
            is_ambient=False,
            prompt_builder=pb,
            chunks=chunks,
            user_message="what is the NOI?",
            recent_messages=[],
            summary_text=None,
            include_history=True,
        )

        pb.build_split.assert_called_once()
        pb.build_ambient_split.assert_not_called()

    def test_single_doc_ambiguous_uses_standard_path(self):
        """Single-doc AMBIGUOUS session uses build_split (not ambient)."""
        pb = self._make_prompt_builder()
        # Single doc → is_ambient is False
        is_ambient = (
            "AMBIGUOUS" == "AMBIGUOUS"
            and bool(["doc1"])
            and len(["doc1"]) > 1  # False → is_ambient = False
        )
        chunks = [_make_chunk("doc1")]

        self._route_prompt(
            is_ambient=is_ambient,
            prompt_builder=pb,
            chunks=chunks,
            user_message="summarize this document",
            recent_messages=[],
            summary_text=None,
            include_history=False,
        )

        pb.build_split.assert_called_once()
        pb.build_ambient_split.assert_not_called()


# ---------------------------------------------------------------------------
# RAGService integration tests — ambient branch wiring
#
# These tests exercise the actual ambient routing logic inside RAGService by
# monkey-patching the reranker and prompt_builder attributes on a stubbed
# RAGService instance.  Because we bypass __init__ (via __new__), we avoid
# importing real SQLAlchemy ORM models and other heavy C-extensions.
#
# Key guarantee: if someone edits rag_service.py to call reranker.rerank()
# instead of reranker.filter_noise() inside the ambient branch, or call
# prompt_builder.build_split() instead of build_ambient_split(), at least one
# test below will fail.
# ---------------------------------------------------------------------------

class _Settings:
    """
    Minimal settings object for rag_service unit tests.

    Unknown attributes fall back to safe defaults (0 / False / empty string)
    so that arithmetic comparisons in rag_service.py don't raise TypeError when
    a new setting is added without updating this stub.
    """

    # Reranker
    rag_use_reranker_chat = True
    rag_use_reranker = True
    rag_reranker_min_candidates_chat = 2
    rag_reranker_ambient_noise_threshold = 0.05
    ambient_top_k = 30

    # Retrieval sizing
    rag_retrieval_candidates = 15
    rag_final_top_k = 8
    rag_scoped_retrieval_candidates = 10
    rag_scoped_final_top_k = 6

    # Budget / context
    rag_context_budget_chars = 10_000
    chat_conversation_char_budget = 15_000
    default_pages_limit = 100
    rag_prompt_version = "v1"

    # Score adjustments
    rag_scope_match_reweight_enabled = True
    rag_scope_match_boost_weight = 0.1
    rag_scope_match_boost_max = 0.3
    rag_scope_mismatch_penalty_weight = 0.05
    rag_scope_penalty_max = 0.2
    rag_scope_guardrail_require_citations = False
    rag_scope_guardrail_regenerate_enabled = False

    # Feature flags
    use_context_expansion = False
    use_fact_extraction = False
    rag_eval_log_enabled = False
    comparison_enabled = False

    # LLM
    synthesis_llm_model = "claude-3-5-haiku-20241022"
    synthesis_llm_max_tokens = 4096
    llm_max_input_chars = 200_000
    synthesis_llm_timeout_seconds = 60
    anthropic_api_key = "test-key"

    def __getattr__(self, name: str):
        # Safe fallback for any unrecognized setting
        return 0


def _make_settings_mock():
    """Return a settings stub safe for arithmetic comparisons."""
    return _Settings()


def _make_rag_service_stub(reranker=None):
    """
    Build a RAGService instance without calling __init__ (bypasses heavy deps).

    All internal collaborators are replaced with mocks so individual method
    calls can be asserted without a live database / embedder / LLM.
    Attribute names match exactly what RAGService.__init__ sets on self.
    """
    from app.core.rag.rag_service import RAGService

    svc = RAGService.__new__(RAGService)

    svc.db = MagicMock()
    svc.embedder = MagicMock()
    svc.llm_client = MagicMock()
    svc.chat_llm_service = MagicMock()
    svc.prompt_builder = MagicMock()
    svc.memory = MagicMock()
    svc.budget_enforcer = MagicMock()
    svc.hybrid_retriever = MagicMock()
    svc.reranker = reranker
    svc.comparison_retriever = MagicMock()
    svc.query_understanding = MagicMock()   # RAGService uses self.query_understanding
    svc.fact_extractor = MagicMock()
    svc.context_expander = MagicMock()
    svc.persistence = MagicMock()           # RAGService uses self.persistence
    svc.comparison_handler = MagicMock()
    svc.document_matcher = MagicMock()
    svc.document_repo = MagicMock()
    svc.budget = MagicMock()
    svc.capture_io_log = False
    svc._io_log = []
    svc.last_comparison_context = None
    svc.last_saved_message_ids = None

    return svc


def _make_query_understanding_result():
    """Return a QueryUnderstanding-like object with sensible defaults."""
    qu = MagicMock()
    # scope_mode must be an object with .value so getattr(qu.scope_mode, "value", None)
    # returns the right string. Setting to None means scope_mode defaults to AMBIGUOUS.
    qu.scope_mode = None
    qu.scope_confidence = 0.0   # Must be < 0.45 to avoid triggering the selection gate
    qu.reformulated_query = "reformulated query"
    qu.rewritten_query = None
    qu.needs_history = False
    qu.query_type = MagicMock()
    qu.query_type.value = "GENERAL_QA"
    qu.query_type.name = "GENERAL_QA"
    qu.confidence = 0.8
    qu.cited_document_ids = []
    qu.is_comparison_query = False
    qu.is_low_signal = False
    qu.entities = []
    qu.target_property_names = []
    qu.target_geo_city = None
    qu.target_geo_state = None
    return qu


def _wire_svc(svc, hybrid_chunks):
    """Configure all async/sync collaborator methods with sensible defaults."""
    qu = _make_query_understanding_result()

    # memory.load_history returns list of messages (not async in actual code)
    svc.memory.load_history = MagicMock(return_value=[])
    svc.memory.will_summarize = MagicMock(return_value=False)
    svc.memory.maybe_summarize = AsyncMock(return_value=(None, [], []))

    svc.query_understanding.understand = AsyncMock(return_value=qu)

    svc.hybrid_retriever.retrieve = MagicMock(return_value=hybrid_chunks)
    svc.budget_enforcer.trim = MagicMock(return_value=hybrid_chunks)
    svc.prompt_builder.build_split = MagicMock(return_value=("sys", "user"))
    svc.prompt_builder.build_ambient_split = MagicMock(return_value=("sys_amb", "user_amb"))

    # persistence.save_chat_messages — used in low_signal and final persist
    svc.persistence.save_chat_messages = AsyncMock(return_value=(MagicMock(), MagicMock()))

    svc.document_repo.get_doc_info_by_ids = MagicMock(return_value=[])
    svc.budget.enforce = AsyncMock(return_value=(None, [], hybrid_chunks))
    svc.document_matcher.match_entities_to_documents = MagicMock(return_value=[])
    svc.document_matcher.match_entities_with_scores = MagicMock(return_value=[])

    async def _fake_stream(*a, **kw):
        yield {"type": "chunk", "text": "answer"}
        yield {"type": "usage", "data": {"input_tokens": 5, "output_tokens": 3}}

    svc.llm_client.stream_chat = _fake_stream

    return svc


def _make_decomp_result(sub_queries=None, was_decomposed=False):
    dr = MagicMock()
    dr.was_decomposed = was_decomposed
    dr.sub_queries = sub_queries or []
    return dr


async def _drain(gen):
    async for _ in gen:
        pass


class TestRAGServiceAmbientBranchWiring:
    """
    Integration tests that drive RAGService.chat through
    the ambient and non-ambient code paths using a fully-stubbed service
    instance (bypasses __init__ via __new__).

    CRITICAL coverage: if the ambient branch in rag_service.py is changed to
    call reranker.rerank() instead of reranker.filter_noise(), or
    prompt_builder.build_split() instead of build_ambient_split(),
    at least one test here will fail.
    """

    @pytest.fixture
    def two_doc_chunks(self):
        return [_make_chunk("doc1"), _make_chunk("doc2"), _make_chunk("doc2", "extra")]

    def _ambient_patches(self):
        """
        Context managers that stub out all the low-level functions imported into
        rag_service at module level so the test can reach the ambient branch.

        Key stubs:
        - is_low_signal_message → False  (otherwise STEP 2 short-circuits)
        - validate_and_normalize_chunks → identity pass-through
        - is_narrow_explicit_fact_lookup → False
        """
        return [
            patch("app.core.rag.rag_service.is_low_signal_message", return_value=False),
            patch("app.core.rag.rag_service.is_narrow_explicit_fact_lookup", return_value=False),
            patch("app.core.rag.rag_service.validate_and_normalize_chunks",
                  side_effect=lambda chunks, **kw: chunks),
        ]

    def _run_chat(self, svc, document_ids, extra_patches=None):
        """Drive svc.chat() to completion with all standard patches applied."""
        import contextlib
        decomp = _make_decomp_result()

        # Collect all patches — order matters: more specific patches last
        all_patches = (
            self._ambient_patches()
            + (extra_patches or [])
            + [
                patch("app.core.rag.rag_service.decompose_and_embed",
                      new=AsyncMock(return_value=decomp)),
                patch("app.core.rag.rag_service.settings", new=_make_settings_mock()),
            ]
        )

        async def run():
            with contextlib.ExitStack() as stack:
                for p in all_patches:
                    stack.enter_context(p)
                async for _ in svc.chat(
                    session_id="sess-t",
                    user_message="what are the cap rates?",
                    collection_id="col-1",
                    document_ids=document_ids,
                ):
                    pass

        asyncio.run(run())

    def test_ambient_uses_filter_noise_not_rerank(self, two_doc_chunks):
        """
        CRITICAL: the ambient path must call filter_noise(), never rerank().

        Changing rag_service.py ambient branch to call reranker.rerank() will
        break this test.
        """
        reranker = MagicMock()
        reranker.filter_noise.return_value = two_doc_chunks
        reranker.rerank.return_value = [two_doc_chunks[0]]

        svc = _wire_svc(_make_rag_service_stub(reranker=reranker), two_doc_chunks)
        self._run_chat(svc, document_ids=["doc1", "doc2"])

        reranker.filter_noise.assert_called_once()
        reranker.rerank.assert_not_called()

    def test_ambient_uses_build_ambient_split(self, two_doc_chunks):
        """
        CRITICAL: the ambient path must call build_ambient_split(), never build_split().

        Changing rag_service.py to call build_split() in the ambient branch will
        break this test.
        """
        reranker = MagicMock()
        reranker.filter_noise.return_value = two_doc_chunks

        svc = _wire_svc(_make_rag_service_stub(reranker=reranker), two_doc_chunks)
        self._run_chat(svc, document_ids=["doc1", "doc2"])

        svc.prompt_builder.build_ambient_split.assert_called_once()
        svc.prompt_builder.build_split.assert_not_called()

    def test_build_citation_context_coerces_missing_page_to_one(self):
        svc = _make_rag_service_stub()
        svc.document_repo.get_doc_info_by_ids = MagicMock(return_value=[
            {"id": "doc-1", "filename": "Florida_Institutional_T12.xlsx"}
        ])

        context = svc._build_citation_context([
            {
                "id": "chunk-1",
                "document_id": "doc-1",
                "page_number": None,
                "chunk_metadata": {"section_heading": "T12 Operating Statement"},
            }
        ])

        assert context["citations"][0]["page"] == 1
        assert context["citations"][0]["filename"] == "Florida_Institutional_T12.xlsx"

    def test_single_doc_ambient_scope_does_not_use_filter_noise(self):
        """
        Single-doc session with AMBIGUOUS scope must NOT trigger ambient path.
        filter_noise() must never be called.
        """
        single_chunk = [_make_chunk("doc1")]
        # Ensure enough candidates so the reranker would be triggered
        three_chunks = single_chunk * 3

        reranker = MagicMock()
        reranker.rerank.return_value = single_chunk
        reranker.filter_noise.return_value = single_chunk

        svc = _wire_svc(_make_rag_service_stub(reranker=reranker), three_chunks)
        svc.budget_enforcer.trim = MagicMock(return_value=single_chunk)
        self._run_chat(svc, document_ids=["doc1"])  # single doc → NOT ambient

        reranker.filter_noise.assert_not_called()


class TestSharedRetrievalSelectionHelpers:
    def test_plan_retrieval_scope_scopes_single_doc_target(self):
        import types
        import app.core.rag.rag_service as rag_service_module

        svc = _make_rag_service_stub(reranker=MagicMock())
        understanding = _make_query_understanding_result()
        understanding.scope_mode = types.SimpleNamespace(
            value=rag_service_module.ScopeMode.SINGLE_DOC.value
        )
        understanding.entities = [MagicMock(entity_type="document")]
        understanding.query_type = rag_service_module.QueryType.SUMMARIZATION
        svc._match_scope_targets_to_documents = MagicMock(return_value=["doc-2"])

        plan = svc._plan_retrieval_scope(
            session_id="sess-1",
            understanding=understanding,
            document_ids=["doc-1", "doc-2"],
            doc_info=[
                {"id": "doc-1", "filename": "Doc One.pdf"},
                {"id": "doc-2", "filename": "Doc Two.pdf"},
            ],
            narrow_explicit_fact_lookup=False,
        )

        assert plan.scope_target_ids == ["doc-2"]
        assert plan.scoped_doc_ids == ["doc-2"]
        assert plan.did_scope_to_single_doc is True
        assert plan.is_ambient is False

    def test_select_retrieval_context_preserves_structured_bypass(self):
        reranker = MagicMock()
        structured_chunk = _make_chunk("doc1", "asking price table")
        structured_chunk["id"] = "table-1"
        structured_chunk["section_type"] = "table"
        structured_chunk["is_keyword_match"] = True
        structured_chunk["raw_rank"] = 9
        structured_chunk["hybrid_score"] = 0.8

        narrative_chunk = _make_chunk("doc1", "narrative chunk")
        narrative_chunk["id"] = "narr-1"
        narrative_chunk["section_type"] = "narrative"
        narrative_chunk["is_keyword_match"] = False
        narrative_chunk["hybrid_score"] = 0.5
        narrative_chunk["rerank_score"] = 0.7

        reranker.rerank.return_value = [narrative_chunk]
        svc = _make_rag_service_stub(reranker=reranker)
        svc._build_document_profiles = MagicMock(return_value={})
        svc._annotate_scope_match_features = MagicMock()
        svc._apply_scope_score_adjustment = MagicMock()
        svc.hybrid_retriever.retrieve = MagicMock(return_value=[structured_chunk, narrative_chunk])

        understanding = _make_query_understanding_result()
        understanding.confidence = 0.9
        settings = _make_settings_mock()
        settings.rag_reranker_skip_confidence_threshold = 0.4
        settings.rag_chat_semantic_similarity_floor = 0.12
        settings.rag_chat_semantic_similarity_floor_no_reranker = 0.25
        settings.rag_reranker_bypass_max_structured = 3
        settings.rag_reranker_min_candidates_chat = 1

        scope_plan = type(svc).RetrievalScopePlan(
            scope_mode="single_doc",
            scope_confidence=0.9,
            scope_target_ids=["doc1"],
            scoped_doc_ids=["doc1"],
            did_scope_to_single_doc=True,
            already_single_doc_scope=False,
            is_ambient=False,
        )

        async def run_test():
            with patch("app.core.rag.rag_service.settings", new=settings):
                return await svc.select_retrieval_context(
                    session_id="sess-1",
                    collection_id=None,
                    user_message="what is the asking price?",
                    understanding=understanding,
                    retrieval_query="asking price",
                    document_ids=["doc1"],
                    retrieval_candidates=15,
                    final_top_k=8,
                    narrow_explicit_fact_lookup=True,
                    doc_info=[{"id": "doc1", "filename": "Doc One.pdf"}],
                    doc_filenames=["Doc One.pdf"],
                    scope_plan=scope_plan,
                )

        result = asyncio.run(run_test())

        reranker.rerank.assert_called_once()
        rerank_chunks = reranker.rerank.call_args.kwargs["chunks"]
        assert [chunk["id"] for chunk in rerank_chunks] == ["narr-1"]
        assert [chunk["id"] for chunk in result["relevant_chunks"][:2]] == ["table-1", "narr-1"]

    def test_select_retrieval_context_a0_uses_semantic_only_dense_baseline(self):
        import app.core.rag.rag_service as rag_service_module

        reranker = MagicMock()
        chunk = _make_chunk("doc1", "dense baseline chunk")
        svc = _make_rag_service_stub(reranker=reranker)
        svc._build_document_profiles = MagicMock(return_value={})
        svc._annotate_scope_match_features = MagicMock()
        svc._apply_scope_score_adjustment = MagicMock()
        svc.hybrid_retriever.retrieve = MagicMock(return_value=[chunk])

        understanding = _make_query_understanding_result()
        understanding.confidence = 0.2
        settings = _make_settings_mock()

        async def run_test():
            with patch("app.core.rag.rag_service.settings", new=settings):
                return await svc.select_retrieval_context(
                    session_id="sess-a0",
                    collection_id=None,
                    user_message="what is the asking price?",
                    understanding=understanding,
                    retrieval_query="asking price",
                    document_ids=["doc1", "doc2"],
                    retrieval_candidates=15,
                    final_top_k=8,
                    narrow_explicit_fact_lookup=True,
                    doc_info=[{"id": "doc1", "filename": "Doc One.pdf"}],
                    doc_filenames=["Doc One.pdf"],
                    ablation_config=rag_service_module.RetrievalAblationConfig.from_id("A0"),
                )

        result = asyncio.run(run_test())

        retrieve_kwargs = svc.hybrid_retriever.retrieve.call_args.kwargs
        assert retrieve_kwargs["use_semantic"] is True
        assert retrieve_kwargs["use_keyword"] is False
        assert retrieve_kwargs["apply_metadata_boost"] is False
        assert reranker.rerank.call_count == 0
        svc._annotate_scope_match_features.assert_not_called()
        svc._apply_scope_score_adjustment.assert_not_called()
        assert result["ablation_id"] == "A0"
        assert result["is_ambient"] is False

    def test_select_retrieval_context_a2_disables_phrase_constraints_and_domain_rerank_helpers(self):
        import app.core.rag.rag_service as rag_service_module

        reranker = MagicMock()
        chunk = _make_chunk("doc1", "generic rerank chunk")
        chunk["id"] = "generic-1"
        reranker.rerank.return_value = [chunk]

        svc = _make_rag_service_stub(reranker=reranker)
        svc._build_document_profiles = MagicMock(return_value={})
        svc._annotate_scope_match_features = MagicMock()
        svc._apply_scope_score_adjustment = MagicMock()
        svc.hybrid_retriever.retrieve = MagicMock(return_value=[chunk])

        understanding = _make_query_understanding_result()
        understanding.confidence = 0.9
        understanding.data_fields = ["asking price"]
        understanding.data_field_synonyms = ["asking price", "offering price"]
        settings = _make_settings_mock()
        settings.rag_reranker_min_candidates_chat = 1

        async def run_test():
            with patch("app.core.rag.rag_service.settings", new=settings):
                return await svc.select_retrieval_context(
                    session_id="sess-a2",
                    collection_id=None,
                    user_message="what is the asking price?",
                    understanding=understanding,
                    retrieval_query="asking price",
                    document_ids=["doc1"],
                    retrieval_candidates=15,
                    final_top_k=8,
                    narrow_explicit_fact_lookup=True,
                    doc_info=[{"id": "doc1", "filename": "Doc One.pdf"}],
                    doc_filenames=["Doc One.pdf"],
                    ablation_config=rag_service_module.RetrievalAblationConfig.from_id("A2"),
                )

        result = asyncio.run(run_test())

        retrieve_kwargs = svc.hybrid_retriever.retrieve.call_args.kwargs
        assert retrieve_kwargs["rq"].lexical_required == []
        assert retrieve_kwargs["rq"].lexical_optional == []
        assert retrieve_kwargs["use_keyword"] is True
        assert retrieve_kwargs["apply_metadata_boost"] is False

        rerank_kwargs = reranker.rerank.call_args.kwargs
        assert rerank_kwargs["apply_metadata_boost"] is False
        assert rerank_kwargs["apply_structured_signal"] is False
        assert result["ablation_id"] == "A2"
