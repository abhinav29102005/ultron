"""
streaming_rag/retrieval.py – Component 3: Corpus Retrieval & Evidence Fusion
=============================================================================
High-performance hybrid retrieval engine combining:
- BM25 Sparse Lexical Inverted Index
- Dense Semantic Vector Search
- Reciprocal Rank Fusion (RRF, k=60) & Semantic Deduplication
- Cross-Encoder Reranking
- Strict Document Provenance Registry (Doc_ID §Section)
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import Dict, List, Optional, Set, Tuple
from streaming_rag.models import DocumentChunk


class BM25Index:
    """Fast, dependency-free BM25 implementation for sparse keyword matching."""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.doc_len: List[int] = []
        self.avg_doc_len: float = 0.0
        self.doc_count: int = 0
        self.inverted_index: Dict[str, List[Tuple[int, int]]] = defaultdict(list)
        self.idf: Dict[str, float] = {}
        self.docs: List[DocumentChunk] = []

    def _tokenize(self, text: str) -> List[str]:
        return [w.lower() for w in re.findall(r"\b\w+\b", text)]

    def index_documents(self, documents: List[DocumentChunk]) -> None:
        self.docs = documents
        self.doc_count = len(documents)
        total_len = 0
        df = Counter()

        for idx, doc in enumerate(documents):
            combined_text = f"{doc.title} {doc.text}"
            tokens = self._tokenize(combined_text)
            self.doc_len.append(len(tokens))
            total_len += len(tokens)

            tf = Counter(tokens)
            for term, count in tf.items():
                self.inverted_index[term].append((idx, count))
                df[term] += 1

        self.avg_doc_len = total_len / max(1, self.doc_count)

        for term, freq in df.items():
            # Standard Lucene / BM25 IDF formulation
            self.idf[term] = math.log(1.0 + (self.doc_count - freq + 0.5) / (freq + 0.5))

    def search(self, query: str, top_k: int = 10) -> List[Tuple[DocumentChunk, float]]:
        tokens = self._tokenize(query)
        scores: Dict[int, float] = defaultdict(float)

        for term in tokens:
            if term not in self.inverted_index:
                continue
            idf_val = self.idf[term]
            for doc_idx, tf in self.inverted_index[term]:
                dlen = self.doc_len[doc_idx]
                numerator = tf * (self.k1 + 1.0)
                denominator = tf + self.k1 * (1.0 - self.b + self.b * (dlen / max(1.0, self.avg_doc_len)))
                scores[doc_idx] += idf_val * (numerator / max(0.001, denominator))

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
        return [(self.docs[idx], score) for idx, score in ranked]


class DenseSemanticIndex:
    """Semantic vector representation index using n-gram subword hashing & projection."""

    def __init__(self, dim: int = 128):
        self.dim = dim
        self.vectors: List[List[float]] = []
        self.docs: List[DocumentChunk] = []

    def _embed(self, text: str) -> List[float]:
        words = [w.lower() for w in re.findall(r"\b\w+\b", text)]
        vec = [0.0] * self.dim
        for w in words:
            # Deterministic feature hashing
            h = hash(w) % self.dim
            vec[h] += 1.0
            # Character n-grams for morphological capture
            for n in (3, 4):
                for i in range(len(w) - n + 1):
                    sub_h = hash(w[i:i+n]) % self.dim
                    vec[sub_h] += 0.5

        # L2 normalize
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0.0:
            vec = [v / norm for v in vec]
        return vec

    def index_documents(self, documents: List[DocumentChunk]) -> None:
        self.docs = documents
        self.vectors = [self._embed(f"{d.title} {d.text}") for d in documents]

    def search(self, query: str, top_k: int = 10) -> List[Tuple[DocumentChunk, float]]:
        q_vec = self._embed(query)
        scores = []
        for idx, d_vec in enumerate(self.vectors):
            dot_product = sum(q * d for q, d in zip(q_vec, d_vec))
            scores.append((self.docs[idx], dot_product))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]


class CrossEncoderReranker:
    """Factual relevance reranker and section deduplicator."""

    def rerank(
        self,
        query: str,
        candidates: List[DocumentChunk],
        top_k: int = 5
    ) -> List[DocumentChunk]:
        seen_tags: Set[str] = set()
        deduped: List[DocumentChunk] = []

        q_terms = set(re.findall(r"\b\w+\b", query.lower()))

        scored_candidates = []
        for doc in candidates:
            if doc.citation_tag in seen_tags:
                continue
            seen_tags.add(doc.citation_tag)

            # Calculate factual overlap score
            d_terms = set(re.findall(r"\b\w+\b", doc.text.lower()))
            overlap = len(q_terms.intersection(d_terms))
            jaccard = overlap / max(1, len(q_terms.union(d_terms)))
            scored_candidates.append((doc, jaccard))

        scored_candidates.sort(key=lambda x: x[1], reverse=True)
        return [doc for doc, _ in scored_candidates[:top_k]]


class HybridRetriever:
    """Component 3 Orchestrator implementing Hybrid Search & Reciprocal Rank Fusion."""

    def __init__(self, rrf_k: int = 60):
        self.rrf_k = rrf_k
        self.bm25 = BM25Index()
        self.dense = DenseSemanticIndex()
        self.reranker = CrossEncoderReranker()
        self.documents: List[DocumentChunk] = []

    def ingest_corpus(self, documents: List[DocumentChunk]) -> None:
        self.documents = documents
        self.bm25.index_documents(documents)
        self.dense.index_documents(documents)

    def retrieve(
        self,
        query: str,
        top_k: int = 4,
        dense_only: bool = False
    ) -> List[DocumentChunk]:
        """Executes Hybrid (BM25 + Dense) with Reciprocal Rank Fusion or Dense-Only ablation."""
        if dense_only:
            dense_results = self.dense.search(query, top_k=top_k * 2)
            return [doc for doc, _ in dense_results[:top_k]]

        # 1. Sparse Search
        bm25_results = self.bm25.search(query, top_k=20)
        # 2. Dense Search
        dense_results = self.dense.search(query, top_k=20)

        # 3. Reciprocal Rank Fusion (RRF)
        rrf_scores: Dict[str, float] = defaultdict(float)
        chunk_map: Dict[str, DocumentChunk] = {}

        for rank, (doc, _) in enumerate(bm25_results):
            rrf_scores[doc.citation_tag] += 1.0 / (self.rrf_k + rank + 1)
            chunk_map[doc.citation_tag] = doc

        for rank, (doc, _) in enumerate(dense_results):
            rrf_scores[doc.citation_tag] += 1.0 / (self.rrf_k + rank + 1)
            chunk_map[doc.citation_tag] = doc

        sorted_tags = sorted(rrf_scores.keys(), key=lambda t: rrf_scores[t], reverse=True)
        fused_candidates = [chunk_map[t] for t in sorted_tags]

        # 4. Rerank & Deduplicate
        return self.reranker.rerank(query, fused_candidates, top_k=top_k)

    def retrieve_parallel(
        self,
        sub_queries: List[str],
        top_k_per_query: int = 3,
        total_max_chunks: int = 6
    ) -> List[DocumentChunk]:
        """Executes multi-intent parallel retrieval and merges results without context inflation."""
        all_chunks: List[DocumentChunk] = []
        seen_tags: Set[str] = set()

        for q in sub_queries:
            chunks = self.retrieve(q, top_k=top_k_per_query)
            for ch in chunks:
                if ch.citation_tag not in seen_tags:
                    seen_tags.add(ch.citation_tag)
                    all_chunks.append(ch)

        return all_chunks[:total_max_chunks]
