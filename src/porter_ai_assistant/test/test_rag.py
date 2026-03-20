# Copyright 2026 VirtusCo
#
# Licensed under the Apache License, Version 2.0 (the 'License');
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an 'AS IS' BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Unit tests for RAG knowledge base retriever."""

import json
import os
import tempfile

from porter_ai_assistant.rag_retriever import (
    DEFAULT_KB_DIR,
    KBDocument,
    KnowledgeBaseRetriever,
    RetrievalResult,
)


# ── Test Data ────────────────────────────────────────────────────────────────

SAMPLE_DOCS = [
    {
        "id": "test_restroom",
        "category": "facilities",
        "title": "Restrooms",
        "content": (
            "Restrooms are located throughout all terminals. Main restroom "
            "locations include near Gates A5, A15, A25. All locations have "
            "accessible restrooms and baby changing stations."
        ),
        "keywords": ["restroom", "bathroom", "toilet", "baby changing"],
    },
    {
        "id": "test_wifi",
        "category": "facilities",
        "title": "WiFi and Internet",
        "content": (
            "Free WiFi is available airport-wide. Connect to "
            "'Airport_Free_WiFi' network and enter your email for a "
            "4-hour session. Premium high-speed passes available."
        ),
        "keywords": ["wifi", "internet", "wireless", "hotspot"],
    },
    {
        "id": "test_taxi",
        "category": "transport",
        "title": "Taxi Services",
        "content": (
            "Taxis are available from Level 0 arrivals. Prepaid taxi "
            "counter near Exit 4. Uber and Ola pickup at Exit 5. "
            "Airport metered taxis outside Exit 6."
        ),
        "keywords": ["taxi", "cab", "uber", "ola", "ride"],
    },
    {
        "id": "test_metro",
        "category": "transport",
        "title": "Metro and Train",
        "content": (
            "Airport Metro station on Level -1. Trains to city centre "
            "every 10-15 minutes. Journey takes 20-30 minutes. "
            "Fare is 60-100 rupees."
        ),
        "keywords": ["metro", "train", "rail", "subway"],
    },
    {
        "id": "test_food",
        "category": "dining",
        "title": "Food Court",
        "content": (
            "Main food court on Level 2 with 15 restaurants including "
            "Indian, fast food, and Asian options. Vegetarian food at "
            "Haldiram's and Dosa Factory. McDonald's and Burger King "
            "for fast food."
        ),
        "keywords": ["food", "restaurant", "eat", "hungry", "dining"],
    },
]


def _create_temp_kb(docs=None):
    """Create a temporary KB directory with test JSON file."""
    tmpdir = tempfile.mkdtemp()
    data = docs or SAMPLE_DOCS
    path = os.path.join(tmpdir, 'test_docs.json')
    with open(path, 'w') as f:
        json.dump(data, f)
    return tmpdir


# ── KBDocument Tests ─────────────────────────────────────────────────────────

class TestKBDocument:
    """Test KBDocument dataclass."""

    def test_basic_document(self):
        """Verify KBDocument construction and defaults."""
        doc = KBDocument(
            id='test', category='cat', title='Title', content='Content',
        )
        assert doc.id == 'test'
        assert doc.keywords == []

    def test_full_text_combines_fields(self):
        """Verify full_text includes title, content, and keywords."""
        doc = KBDocument(
            id='t', category='c', title='My Title',
            content='My content here.',
            keywords=['alpha', 'beta'],
        )
        full = doc.full_text
        assert 'My Title' in full
        assert 'My content here.' in full
        assert 'alpha' in full
        assert 'beta' in full


# ── KnowledgeBaseRetriever Loading Tests ─────────────────────────────────────

class TestRetrieverLoading:
    """Test KB loading and indexing."""

    def test_load_from_directory(self):
        """Verify documents load from JSON directory."""
        tmpdir = _create_temp_kb()
        retriever = KnowledgeBaseRetriever(kb_dir=tmpdir)
        assert len(retriever.documents) == 5
        assert retriever._indexed is True

    def test_load_empty_directory(self):
        """Verify loading from empty directory returns zero docs."""
        tmpdir = tempfile.mkdtemp()
        retriever = KnowledgeBaseRetriever(kb_dir=tmpdir)
        assert len(retriever.documents) == 0
        assert retriever._indexed is False

    def test_load_nonexistent_directory(self):
        """Verify graceful handling of missing directory."""
        retriever = KnowledgeBaseRetriever(kb_dir='/nonexistent/path')
        assert len(retriever.documents) == 0

    def test_load_invalid_json(self):
        """Verify graceful handling of malformed JSON."""
        tmpdir = tempfile.mkdtemp()
        with open(os.path.join(tmpdir, 'bad.json'), 'w') as f:
            f.write('not valid json {{{')
        retriever = KnowledgeBaseRetriever(kb_dir=tmpdir)
        assert len(retriever.documents) == 0

    def test_stats_after_load(self):
        """Verify stats reflect loaded state."""
        tmpdir = _create_temp_kb()
        retriever = KnowledgeBaseRetriever(kb_dir=tmpdir)
        stats = retriever.stats
        assert stats['num_documents'] == 5
        assert stats['num_terms'] > 0
        assert stats['num_keywords'] > 0
        assert stats['indexed'] is True


# ── Tokenizer Tests ──────────────────────────────────────────────────────────

class TestTokenizer:
    """Test the internal tokenizer."""

    def test_basic_tokenization(self):
        """Verify basic text tokenizes to lowercase terms."""
        retriever = KnowledgeBaseRetriever(kb_dir=None)
        retriever.documents = []  # Don't load default KB
        tokens = retriever._tokenize('Where is the nearest restroom?')
        assert 'nearest' in tokens
        assert 'restroom' in tokens
        # Stop words filtered
        assert 'is' not in tokens
        assert 'the' not in tokens

    def test_empty_string(self):
        """Verify empty string returns empty token list."""
        retriever = KnowledgeBaseRetriever(kb_dir=None)
        retriever.documents = []
        assert retriever._tokenize('') == []

    def test_preserves_hyphenated_words(self):
        """Verify hyphenated words are kept together."""
        retriever = KnowledgeBaseRetriever(kb_dir=None)
        retriever.documents = []
        tokens = retriever._tokenize('duty-free shopping')
        assert 'duty-free' in tokens

    def test_numbers_preserved(self):
        """Verify numbers are preserved as tokens."""
        retriever = KnowledgeBaseRetriever(kb_dir=None)
        retriever.documents = []
        tokens = retriever._tokenize('Gate A15 on Level 2')
        assert 'a15' in tokens
        assert 'level' in tokens


# ── Retrieval Tests ──────────────────────────────────────────────────────────

class TestRetrieval:
    """Test document retrieval quality."""

    def test_restroom_query(self):
        """Verify restroom query retrieves restroom document."""
        tmpdir = _create_temp_kb()
        retriever = KnowledgeBaseRetriever(kb_dir=tmpdir)
        results = retriever.retrieve('Where is the nearest restroom?')
        assert len(results) > 0
        # Top result should be restroom
        assert results[0].doc.id == 'test_restroom'
        assert results[0].score > 0

    def test_wifi_query(self):
        """Verify WiFi query retrieves WiFi document."""
        tmpdir = _create_temp_kb()
        retriever = KnowledgeBaseRetriever(kb_dir=tmpdir)
        results = retriever.retrieve('How do I connect to WiFi?')
        assert len(results) > 0
        top_ids = [r.doc.id for r in results]
        assert 'test_wifi' in top_ids

    def test_taxi_query(self):
        """Verify taxi query retrieves transport document."""
        tmpdir = _create_temp_kb()
        retriever = KnowledgeBaseRetriever(kb_dir=tmpdir)
        results = retriever.retrieve('I need a taxi to the city')
        assert len(results) > 0
        assert results[0].doc.id == 'test_taxi'

    def test_food_query(self):
        """Verify food query retrieves dining document."""
        tmpdir = _create_temp_kb()
        retriever = KnowledgeBaseRetriever(kb_dir=tmpdir)
        results = retriever.retrieve("I'm hungry, where can I eat?")
        assert len(results) > 0
        top_ids = [r.doc.id for r in results]
        assert 'test_food' in top_ids

    def test_keyword_boosting(self):
        """Verify keyword matches boost document scores."""
        tmpdir = _create_temp_kb()
        retriever = KnowledgeBaseRetriever(kb_dir=tmpdir)
        # 'uber' is a keyword for taxi doc
        results = retriever.retrieve('Where is the Uber pickup?')
        assert len(results) > 0
        assert results[0].doc.id == 'test_taxi'

    def test_category_filter(self):
        """Verify category filter limits results."""
        tmpdir = _create_temp_kb()
        retriever = KnowledgeBaseRetriever(kb_dir=tmpdir)
        results = retriever.retrieve(
            'Where can I find food?', category_filter='transport',
        )
        # Should not return food doc (dining category)
        for r in results:
            assert r.doc.category == 'transport'

    def test_top_k_limits_results(self):
        """Verify top_k parameter limits result count."""
        tmpdir = _create_temp_kb()
        retriever = KnowledgeBaseRetriever(kb_dir=tmpdir, top_k=2)
        results = retriever.retrieve('airport services')
        assert len(results) <= 2

    def test_min_score_threshold(self):
        """Verify min_score filters low-scoring results."""
        tmpdir = _create_temp_kb()
        retriever = KnowledgeBaseRetriever(
            kb_dir=tmpdir, min_score=0.9,
        )
        results = retriever.retrieve('random unrelated query xyz')
        # Very unlikely to exceed 0.9 threshold
        assert len(results) == 0

    def test_empty_query(self):
        """Verify empty query returns no results."""
        tmpdir = _create_temp_kb()
        retriever = KnowledgeBaseRetriever(kb_dir=tmpdir)
        results = retriever.retrieve('')
        assert len(results) == 0

    def test_no_index_returns_empty(self):
        """Verify retrieval on unindexed retriever returns empty."""
        retriever = KnowledgeBaseRetriever(kb_dir=None)
        retriever.documents = []
        retriever._indexed = False
        results = retriever.retrieve('test query')
        assert results == []


# ── Context Building Tests ───────────────────────────────────────────────────

class TestBuildContext:
    """Test context string building for LLM injection."""

    def test_basic_context(self):
        """Verify context string includes document title and content."""
        tmpdir = _create_temp_kb()
        retriever = KnowledgeBaseRetriever(kb_dir=tmpdir)
        context = retriever.build_context('Where is the bathroom?')
        assert 'Relevant airport information:' in context
        assert 'Restrooms' in context

    def test_empty_context_for_unmatched(self):
        """Verify empty context for completely unrelated query."""
        tmpdir = _create_temp_kb()
        retriever = KnowledgeBaseRetriever(
            kb_dir=tmpdir, min_score=0.9,
        )
        context = retriever.build_context('xyz qqq zzz')
        assert context == ''

    def test_context_respects_max_chars(self):
        """Verify context is truncated within max_context_chars."""
        tmpdir = _create_temp_kb()
        retriever = KnowledgeBaseRetriever(
            kb_dir=tmpdir, max_context_chars=200,
        )
        context = retriever.build_context('airport food taxi restroom')
        # Header is ~30 chars, so total should be under 250
        assert len(context) < 300

    def test_context_with_no_retriever_docs(self):
        """Verify empty context when no documents loaded."""
        retriever = KnowledgeBaseRetriever(kb_dir=None)
        retriever.documents = []
        retriever._indexed = False
        context = retriever.build_context('hello')
        assert context == ''


# ── Real Knowledge Base Tests ────────────────────────────────────────────────

class TestRealKnowledgeBase:
    """Test retriever against the actual airport knowledge base (if present)."""

    def test_real_kb_loads(self):
        """Verify real knowledge base loads from default directory."""
        if not DEFAULT_KB_DIR.is_dir():
            return  # Skip if KB not present
        retriever = KnowledgeBaseRetriever()
        assert len(retriever.documents) > 0
        assert retriever._indexed is True

    def test_real_kb_restroom_query(self):
        """Verify real KB returns relevant restroom information."""
        if not DEFAULT_KB_DIR.is_dir():
            return
        retriever = KnowledgeBaseRetriever()
        results = retriever.retrieve('Where is the nearest restroom?')
        assert len(results) > 0
        titles = [r.doc.title.lower() for r in results]
        assert any('restroom' in t for t in titles)

    def test_real_kb_flight_query(self):
        """Verify real KB returns relevant check-in information."""
        if not DEFAULT_KB_DIR.is_dir():
            return
        retriever = KnowledgeBaseRetriever()
        results = retriever.retrieve('How do I check in for my flight?')
        assert len(results) > 0

    def test_real_kb_transport_query(self):
        """Verify real KB returns transport info for taxi query."""
        if not DEFAULT_KB_DIR.is_dir():
            return
        retriever = KnowledgeBaseRetriever()
        results = retriever.retrieve('How do I get a taxi?')
        assert len(results) > 0
        top_ids = [r.doc.id for r in results]
        assert any('taxi' in tid or 'transport' in tid for tid in top_ids)

    def test_real_kb_context_building(self):
        """Verify context building produces non-empty output for real KB."""
        if not DEFAULT_KB_DIR.is_dir():
            return
        retriever = KnowledgeBaseRetriever()
        context = retriever.build_context('Where can I eat?')
        assert 'Relevant airport information:' in context
        assert len(context) > 50
