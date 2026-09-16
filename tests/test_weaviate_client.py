"""Basic import test for Weaviate client wrapper."""

import pytest

from intelligence import weaviate_client


def test_weaviate_wrapper_importable():
    # The wrapper should import even if weaviate is not installed; constructing
    # the client requires a real server and package, so we just ensure the
    # symbol exists.
    assert hasattr(weaviate_client, "WeaviateClientWrapper")


def test_weaviate_ingest_includes_doc_id_and_section(monkeypatch):
    """Ensure ingest_documents forwards doc_id and section into Weaviate objects."""
    from unittest.mock import MagicMock
    from intelligence.weaviate_client import WeaviateClientWrapper

    # Mock weaviate.Client creation
    mock_client = MagicMock()
    mock_batch = MagicMock()
    mock_client.batch = mock_batch
    mock_batch.__enter__.return_value = mock_batch

    # Mock schema check
    mock_client.schema.get.return_value = {"classes": [{"class": "UltronDocument"}]}

    monkeypatch.setattr("weaviate.Client", lambda **kwargs: mock_client)

    wrapper = WeaviateClientWrapper(url="http://localhost:8080")
    docs = [
        {
            "title": "Corporate Travel Policy",
            "url": "https://example.com/travel",
            "snippet": "Travel rules",
            "content": "Full reimbursement requires receipts.",
            "source": "web",
            "doc_id": "Doc_45",
            "section": "§1",
        }
    ]

    wrapper.ingest_documents(docs)

    assert mock_batch.add_data_object.called
    added_obj, class_name = mock_batch.add_data_object.call_args[0]
    assert class_name == "UltronDocument"
    assert added_obj["doc_id"] == "Doc_45"
    assert added_obj["section"] == "§1"
    assert added_obj["title"] == "Corporate Travel Policy"


def test_weaviate_vector_search_returns_doc_id_and_section(monkeypatch):
    """Ensure vector_search requests and extracts doc_id and section properties."""
    from unittest.mock import MagicMock
    from intelligence.weaviate_client import WeaviateClientWrapper

    mock_client = MagicMock()
    mock_query = MagicMock()
    mock_get = MagicMock()
    mock_client.query = mock_query
    mock_query.get.return_value = mock_get
    mock_get.with_near_text.return_value = mock_get
    mock_get.with_limit.return_value = mock_get

    mock_get.do.return_value = {
        "data": {
            "Get": {
                "UltronDocument": [
                    {
                        "properties": {
                            "title": "Venue Capacity",
                            "url": "https://example.com/venue",
                            "snippet": "Pune workshop",
                            "content": "Capacity 30 people.",
                            "source": "weaviate",
                            "doc_id": "Doc_12",
                            "section": "§2",
                        }
                    }
                ]
            }
        }
    }

    monkeypatch.setattr("weaviate.Client", lambda **kwargs: mock_client)

    wrapper = WeaviateClientWrapper(url="http://localhost:8080")
    results = wrapper.vector_search(query="Pune workshop 30 people", top_k=1)

    assert len(results) == 1
    # Verify query.get asked for doc_id and section
    requested_props = mock_query.get.call_args[0][1]
    assert "doc_id" in requested_props
    assert "section" in requested_props

    # Verify extracted results have doc_id and section
    assert results[0]["doc_id"] == "Doc_12"
    assert results[0]["section"] == "§2"
