"""
intelligence/weaviate_client.py
================================

Lightweight Weaviate client wrapper used by the hybrid retriever.
Provides schema creation, document ingestion (batch), and vector search.

This module is defensive: it only activates when the `weaviate` package is
installed and a `WEAVIATE_URL` is configured in settings. Installation is
documented in project setup; the wrapper logs a clear error when missing.
"""

from __future__ import annotations

from typing import List, Dict, Any
import logging

logger = logging.getLogger("weaviate_client")


class WeaviateUnavailable(Exception):
    pass


class WeaviateClientWrapper:
    def __init__(self, url: str, api_key: str | None = None, index_name: str = "UltronDocument"):
        try:
            import weaviate
        except Exception as exc:
            logger.exception("Weaviate client not installed: {}", exc)
            raise WeaviateUnavailable("weaviate client not installed") from exc

        self._weaviate = weaviate
        self._client_kwargs = {"url": url}
        if api_key:
            # Support simple API key header configuration
            self._client_kwargs["auth_client_secret"] = weaviate.AuthApiKey(api_key)

        self.client = weaviate.Client(**self._client_kwargs)
        self.index_name = index_name

    def ensure_schema(self) -> None:
        schema = self.client.schema.get()
        classes = [c["class"] for c in (schema.get("classes") or [])]
        if self.index_name in classes:
            return

        class_obj = {
            "class": self.index_name,
            "vectorizer": "text2vec-transformers",
            "properties": [
                {"name": "title", "dataType": ["text"]},
                {"name": "url", "dataType": ["text"]},
                {"name": "snippet", "dataType": ["text"]},
                {"name": "content", "dataType": ["text"]},
                {"name": "source", "dataType": ["text"]},
                {"name": "doc_id", "dataType": ["text"]},
                {"name": "section", "dataType": ["text"]},
            ],
        }

        try:
            self.client.schema.create_class(class_obj)
            logger.info("Weaviate schema created for class {}", self.index_name)
        except Exception:
            logger.exception("Failed to create Weaviate schema; continuing without it")

    def ingest_documents(self, docs: List[Dict[str, Any]]) -> None:
        """Batch ingest documents into the Weaviate instance.

        Each doc should be a dict with keys: title, url, snippet, content, source, doc_id, section.
        """
        if not docs:
            return

        try:
            self.ensure_schema()
            batch = self.client.batch
            batch.batch_size = 50
            batch.flush_interval = 1
            with batch as b:
                for doc in docs:
                    obj = {
                        "title": doc.get("title", ""),
                        "url": doc.get("url", ""),
                        "snippet": doc.get("snippet", ""),
                        "content": doc.get("content", ""),
                        "source": doc.get("source", "web"),
                        "doc_id": doc.get("doc_id", ""),
                        "section": doc.get("section", ""),
                    }
                    b.add_data_object(obj, self.index_name)
            logger.info("Indexed {} documents into Weaviate class {}", len(docs), self.index_name)
        except Exception:
            logger.exception("Weaviate ingestion failed; continuing without vector index")

    def vector_search(self, query: str | None = None, embedding: List[float] | None = None, top_k: int = 5) -> List[Dict[str, Any]]:
        """Perform a vector search using either raw `query` (nearText) or a precomputed `embedding` (nearVector).

        Returns a list of lightweight document dicts including doc_id and section.
        """
        try:
            q = self.client.query.get(self.index_name, ["title", "url", "snippet", "content", "source", "doc_id", "section"])  # type: ignore

            if embedding is not None:
                q = q.with_near_vector({"vector": embedding})
            elif query is not None:
                q = q.with_near_text({"concepts": [query]})
            else:
                raise ValueError("Either 'query' or 'embedding' must be provided")

            res = q.with_limit(top_k).do()

            objs = []
            for item in (res.get("data", {}).get("Get", {}).get(self.index_name) or []):
                props = item.get("properties", {})
                objs.append({
                    "title": props.get("title", ""),
                    "url": props.get("url", ""),
                    "snippet": props.get("snippet", ""),
                    "content": props.get("content", ""),
                    "source": props.get("source", "weaviate"),
                    "doc_id": props.get("doc_id", ""),
                    "section": props.get("section", ""),
                })
            return objs
        except Exception:
            logger.exception("Weaviate vector search failed")
            return []
