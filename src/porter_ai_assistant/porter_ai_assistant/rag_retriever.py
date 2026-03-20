# Copyright 2026 VirtusCo
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Lightweight RAG (Retrieval-Augmented Generation) module for Virtue.

Retrieves relevant airport knowledge base chunks and injects them as
context into the LLM prompt. Uses TF-IDF + keyword boosting for
retrieval — no heavy embedding models required (RPi-friendly).

Architecture:
    Knowledge Base (JSON files)
        → Index (TF-IDF vectorizer + keyword index)
        → Retriever (score + rank + deduplicate)
        → Context Builder (format top-k chunks for LLM prompt)

The knowledge base is loaded from JSON files in:
    data/knowledge_base/*.json

Each document has: id, category, title, content, keywords.
"""

from dataclasses import dataclass, field
import json
import logging
import math
import os
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Default paths
DEFAULT_KB_DIR = Path(__file__).resolve().parent.parent / 'data' / 'knowledge_base'

# Retrieval defaults
DEFAULT_TOP_K = 3
DEFAULT_MIN_SCORE = 0.05
DEFAULT_MAX_CONTEXT_CHARS = 1200


@dataclass
class KBDocument:
    """Single knowledge base document."""

    id: str
    category: str
    title: str
    content: str
    keywords: List[str] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        """Combine title, content, and keywords for indexing."""
        parts = [self.title, self.content]
        if self.keywords:
            parts.append(' '.join(self.keywords))
        return ' '.join(parts)


@dataclass
class RetrievalResult:
    """Result from a knowledge base retrieval."""

    doc: KBDocument
    score: float
    match_source: str = ''  # 'tfidf', 'keyword', 'combined'


class KnowledgeBaseRetriever:
    """Lightweight TF-IDF + keyword retrieval for airport knowledge base.

    Designed for RPi deployment: no GPU, no embedding model, no external
    dependencies beyond standard Python. Uses in-memory inverted index
    with TF-IDF scoring and keyword boosting.

    Attributes:
        documents: List of loaded KBDocument instances.
        top_k: Number of results to return.
        min_score: Minimum relevance score threshold.
    """

    def __init__(
        self,
        kb_dir: Optional[str] = None,
        top_k: int = DEFAULT_TOP_K,
        min_score: float = DEFAULT_MIN_SCORE,
        max_context_chars: int = DEFAULT_MAX_CONTEXT_CHARS,
    ):
        """Initialise the retriever.

        Args:
            kb_dir: Path to knowledge base JSON directory.
            top_k: Maximum number of results to return.
            min_score: Minimum score to include a result.
            max_context_chars: Max total characters in context string.
        """
        self.documents: List[KBDocument] = []
        self.top_k = top_k
        self.min_score = min_score
        self.max_context_chars = max_context_chars

        # TF-IDF index structures
        self._doc_freqs: Dict[str, int] = {}   # term → num docs containing it
        self._doc_tfidf: List[Dict[str, float]] = []  # per-doc TF-IDF vectors
        self._keyword_index: Dict[str, List[int]] = {}  # keyword → doc indices
        self._indexed = False
        self._num_docs = 0

        # Load KB if directory provided
        if kb_dir:
            self.load(kb_dir)
        elif DEFAULT_KB_DIR.is_dir():
            self.load(str(DEFAULT_KB_DIR))

    def load(self, kb_dir: str) -> int:
        """Load knowledge base documents from JSON files.

        Args:
            kb_dir: Directory containing JSON knowledge base files.

        Returns:
            Number of documents loaded.
        """
        kb_path = Path(kb_dir)
        if not kb_path.is_dir():
            logger.warning('Knowledge base directory not found: %s', kb_dir)
            return 0

        self.documents.clear()
        count = 0

        for json_file in sorted(kb_path.glob('*.json')):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    docs = json.load(f)
                for doc_data in docs:
                    doc = KBDocument(
                        id=doc_data.get('id', f'doc_{count}'),
                        category=doc_data.get('category', ''),
                        title=doc_data.get('title', ''),
                        content=doc_data.get('content', ''),
                        keywords=doc_data.get('keywords', []),
                    )
                    if doc.content.strip():
                        self.documents.append(doc)
                        count += 1
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                logger.warning('Error loading %s: %s', json_file.name, e)

        if count > 0:
            self._build_index()
            logger.info(
                'Loaded %d knowledge base documents from %s',
                count, kb_dir,
            )
        else:
            logger.warning('No documents loaded from %s', kb_dir)

        return count

    def _tokenize(self, text: str) -> List[str]:
        """Tokenize text into lowercase terms for indexing.

        Args:
            text: Input text.

        Returns:
            List of lowercase token strings.
        """
        # Simple whitespace + punctuation tokenizer
        text = text.lower()
        # Keep alphanumeric, hyphens, apostrophes
        tokens = re.findall(r"[a-z0-9]+(?:[-'][a-z0-9]+)*", text)
        # Remove very short or very common stop words
        stop_words = {
            'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'been',
            'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
            'would', 'could', 'should', 'may', 'might', 'can', 'shall',
            'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by', 'from',
            'as', 'into', 'through', 'during', 'before', 'after', 'above',
            'below', 'between', 'out', 'off', 'over', 'under', 'again',
            'further', 'then', 'once', 'here', 'there', 'when', 'where',
            'why', 'how', 'all', 'both', 'each', 'few', 'more', 'most',
            'other', 'some', 'such', 'no', 'nor', 'not', 'only', 'own',
            'same', 'so', 'than', 'too', 'very', 'just', 'about', 'also',
            'and', 'but', 'or', 'if', 'it', 'its', 'i', 'me', 'my',
            'we', 'you', 'your', 'he', 'she', 'they', 'them', 'this',
            'that', 'these', 'those', 'what', 'which', 'who', 'whom',
        }
        return [t for t in tokens if len(t) > 1 and t not in stop_words]

    def _build_index(self) -> None:
        """Build TF-IDF and keyword indices from loaded documents."""
        t_start = time.monotonic()
        self._num_docs = len(self.documents)
        self._doc_freqs = {}
        self._doc_tfidf = []
        self._keyword_index = {}

        # Step 1: Compute term frequencies per document
        doc_term_freqs: List[Dict[str, int]] = []
        for doc in self.documents:
            tokens = self._tokenize(doc.full_text)
            tf: Dict[str, int] = {}
            for token in tokens:
                tf[token] = tf.get(token, 0) + 1
            doc_term_freqs.append(tf)

        # Step 2: Document frequencies
        for tf in doc_term_freqs:
            for term in tf:
                self._doc_freqs[term] = self._doc_freqs.get(term, 0) + 1

        # Step 3: TF-IDF vectors (log-normalised TF × IDF)
        for tf in doc_term_freqs:
            tfidf: Dict[str, float] = {}
            if not tf:
                self._doc_tfidf.append(tfidf)
                continue
            max_tf = max(tf.values())
            for term, count in tf.items():
                # Augmented TF: 0.5 + 0.5 * (tf / max_tf)
                norm_tf = 0.5 + 0.5 * (count / max_tf)
                df = self._doc_freqs.get(term, 1)
                idf = math.log((self._num_docs + 1) / (df + 1)) + 1
                tfidf[term] = norm_tf * idf
            # L2 normalise
            magnitude = math.sqrt(sum(v * v for v in tfidf.values()))
            if magnitude > 0:
                for term in tfidf:
                    tfidf[term] /= magnitude
            self._doc_tfidf.append(tfidf)

        # Step 4: Keyword inverse index
        for idx, doc in enumerate(self.documents):
            for kw in doc.keywords:
                kw_lower = kw.lower()
                if kw_lower not in self._keyword_index:
                    self._keyword_index[kw_lower] = []
                self._keyword_index[kw_lower].append(idx)
                # Also index individual words in multi-word keywords
                for word in kw_lower.split():
                    if word not in self._keyword_index:
                        self._keyword_index[word] = []
                    if idx not in self._keyword_index[word]:
                        self._keyword_index[word].append(idx)

        self._indexed = True
        elapsed = (time.monotonic() - t_start) * 1000
        logger.info(
            'Built index: %d docs, %d terms, %d keywords in %.1fms',
            self._num_docs, len(self._doc_freqs),
            len(self._keyword_index), elapsed,
        )

    def _compute_query_tfidf(
        self, query_tokens: List[str],
    ) -> Dict[str, float]:
        """Compute TF-IDF vector for a query.

        Args:
            query_tokens: Tokenized query.

        Returns:
            Dict mapping terms to TF-IDF weights.
        """
        tf: Dict[str, int] = {}
        for token in query_tokens:
            tf[token] = tf.get(token, 0) + 1

        if not tf:
            return {}

        max_tf = max(tf.values())
        tfidf: Dict[str, float] = {}
        for term, count in tf.items():
            norm_tf = 0.5 + 0.5 * (count / max_tf)
            df = self._doc_freqs.get(term, 0)
            if df == 0:
                # Term not in corpus — still give it some weight
                idf = math.log((self._num_docs + 1) / 1) + 1
            else:
                idf = math.log((self._num_docs + 1) / (df + 1)) + 1
            tfidf[term] = norm_tf * idf

        # L2 normalise
        magnitude = math.sqrt(sum(v * v for v in tfidf.values()))
        if magnitude > 0:
            for term in tfidf:
                tfidf[term] /= magnitude

        return tfidf

    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        category_filter: Optional[str] = None,
    ) -> List[RetrievalResult]:
        """Retrieve relevant documents for a query.

        Uses combined TF-IDF cosine similarity + keyword matching.
        Keyword matches get a boost to favour exact-match relevance.

        Args:
            query: User query text.
            top_k: Override default top_k.
            category_filter: Limit to specific category (optional).

        Returns:
            Sorted list of RetrievalResult, highest score first.
        """
        if not self._indexed or not self.documents:
            return []

        k = top_k or self.top_k
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        # TF-IDF cosine similarity
        query_vec = self._compute_query_tfidf(query_tokens)
        tfidf_scores: List[float] = []
        for doc_vec in self._doc_tfidf:
            score = sum(
                query_vec.get(term, 0) * doc_vec.get(term, 0)
                for term in query_vec
            )
            tfidf_scores.append(score)

        # Keyword boosting
        keyword_scores: List[float] = [0.0] * self._num_docs
        query_lower = query.lower()
        for kw, doc_indices in self._keyword_index.items():
            if kw in query_lower:
                for idx in doc_indices:
                    keyword_scores[idx] += 0.15  # Boost per keyword match

        # Combined score: TF-IDF + keyword boost
        combined: List[Tuple[int, float]] = []
        for idx in range(self._num_docs):
            if category_filter:
                if self.documents[idx].category != category_filter:
                    continue
            score = tfidf_scores[idx] + keyword_scores[idx]
            if score >= self.min_score:
                combined.append((idx, score))

        combined.sort(key=lambda x: x[1], reverse=True)

        results = []
        for idx, score in combined[:k]:
            doc = self.documents[idx]
            if keyword_scores[idx] > 0 and tfidf_scores[idx] > 0:
                source = 'combined'
            elif keyword_scores[idx] > 0:
                source = 'keyword'
            else:
                source = 'tfidf'
            results.append(RetrievalResult(
                doc=doc,
                score=round(score, 4),
                match_source=source,
            ))

        return results

    def build_context(
        self,
        query: str,
        top_k: Optional[int] = None,
        category_filter: Optional[str] = None,
    ) -> str:
        """Retrieve and format knowledge base context for LLM injection.

        Returns a formatted string suitable for prepending to the user's
        context in the inference pipeline.

        Args:
            query: User query text.
            top_k: Override default top_k.
            category_filter: Limit to specific category.

        Returns:
            Formatted context string, or empty string if no matches.
        """
        results = self.retrieve(query, top_k, category_filter)
        if not results:
            return ''

        parts = []
        total_chars = 0
        for r in results:
            chunk = f'[{r.doc.title}]: {r.doc.content}'
            if total_chars + len(chunk) > self.max_context_chars:
                # Truncate to fit budget
                remaining = self.max_context_chars - total_chars
                if remaining > 100:
                    chunk = chunk[:remaining] + '...'
                    parts.append(chunk)
                break
            parts.append(chunk)
            total_chars += len(chunk)

        if not parts:
            return ''

        context = 'Relevant airport information:\n' + '\n'.join(parts)
        return context

    @property
    def stats(self) -> Dict:
        """Index statistics.

        Returns:
            Dict with document count, term count, and indexed flag.
        """
        return {
            'num_documents': len(self.documents),
            'num_terms': len(self._doc_freqs),
            'num_keywords': len(self._keyword_index),
            'indexed': self._indexed,
            'max_context_chars': self.max_context_chars,
            'top_k': self.top_k,
        }
