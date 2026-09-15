"""Basic import test for Weaviate client wrapper."""

import pytest

from intelligence import weaviate_client


def test_weaviate_wrapper_importable():
    # The wrapper should import even if weaviate is not installed; constructing
    # the client requires a real server and package, so we just ensure the
    # symbol exists.
    assert hasattr(weaviate_client, "WeaviateClientWrapper")
