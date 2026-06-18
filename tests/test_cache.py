import pytest
import time
from unittest.mock import patch

from src.core.cache import MemoryCache

@pytest.fixture
def cache():
    """Provides a fresh MemoryCache instance for each test."""
    return MemoryCache()

def test_set_get_roundtrip(cache):
    """Test that a value can be set and retrieved."""
    cache.set("test_key", "test_value")
    assert cache.get("test_key") == "test_value"

def test_get_missing_key(cache):
    """Test that retrieving a missing key returns None."""
    assert cache.get("nonexistent_key") is None

def test_ttl_expiry(cache):
    """Test that items expire after their TTL."""
    # Set with TTL of 1 second (short TTL)
    cache.set("temp_key", "temp_val", ttl=1)
    assert cache.get("temp_key") == "temp_val"

    # Wait past the TTL
    time.sleep(1.1)

    # Value should be expired
    assert cache.get("temp_key") is None

def test_delete(cache):
    """Test that an item can be deleted."""
    cache.set("del_key", "del_val")
    assert cache.get("del_key") == "del_val"

    result = cache.delete("del_key")
    assert result is True
    assert cache.get("del_key") is None

    # Deleting a non-existent key should return False
    result = cache.delete("del_key")
    assert result is False

def test_clear_namespace(cache):
    """Test that clear empties the cache for a specific namespace."""
    cache.set("key1", "val1", namespace="ns1")
    cache.set("key2", "val2", namespace="ns1")
    cache.set("key3", "val3", namespace="ns2")

    # Clear ns1
    cache.clear_namespace("ns1")

    # ns1 keys should be gone
    assert cache.get("key1", namespace="ns1") is None
    assert cache.get("key2", namespace="ns1") is None

    # ns2 keys should remain
    assert cache.get("key3", namespace="ns2") == "val3"

def test_clear(cache):
    """Test that cache can be completely emptied."""
    # The current cache only supports clearing by namespace.
    # We will test clear_namespace on default and other namespaces.
    cache.set("key1", "val1")
    cache.set("key2", "val2", namespace="other")

    cache.clear_namespace() # clears default
    assert cache.get("key1") is None
    assert cache.get("key2", namespace="other") == "val2"

    cache.clear_namespace("other")
    assert cache.get("key2", namespace="other") is None

def test_namespace_isolation(cache):
    """Test that same keys in different namespaces are isolated."""
    cache.set("shared_key", "value_a", namespace="nsA")
    cache.set("shared_key", "value_b", namespace="nsB")

    assert cache.get("shared_key", namespace="nsA") == "value_a"
    assert cache.get("shared_key", namespace="nsB") == "value_b"
