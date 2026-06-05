import pytest
from src.core.database import DatabaseManager

@pytest.fixture
def db():
    # Use in-memory SQLite for testing
    manager = DatabaseManager(":memory:")
    # Initialize schema happens automatically

    # Add some test assets
    manager.add_or_update_asset({"symbol": "AAPL", "name": "Apple Inc.", "asset_type": "stock"})
    manager.add_or_update_asset({"symbol": "AAP_L", "name": "Apple Underscore", "asset_type": "stock"})
    manager.add_or_update_asset({"symbol": "AAP%L", "name": "Apple Percent", "asset_type": "stock"})
    manager.add_or_update_asset({"symbol": "MSFT", "name": "Microsoft Corporation", "asset_type": "stock"})

    yield manager

    manager.close()

def test_search_assets_wildcard_escaping(db):
    """Test that SQL wildcards (%) and (_) are properly escaped."""
    # Searching for literal underscore should only return the asset with an underscore
    results_underscore = db.search_assets("AAP_")
    assert len(results_underscore) == 1
    assert results_underscore[0]['symbol'] == "AAP_L"

    # Searching for literal percent should only return the asset with a percent
    results_percent = db.search_assets("AAP%")
    assert len(results_percent) == 1
    assert results_percent[0]['symbol'] == "AAP%L"

    # Searching for literal backslash
    db.add_or_update_asset({"symbol": "AAP\\L", "name": "Apple Backslash", "asset_type": "stock"})
    results_backslash = db.search_assets("AAP\\")
    assert len(results_backslash) == 1
    assert results_backslash[0]['symbol'] == "AAP\\L"

def test_search_assets_length_limit(db):
    """Test that extremely long queries are truncated."""
    # This shouldn't crash or cause ReDoS due to truncation
    long_query = "A" * 1000
    results = db.search_assets(long_query)
    assert len(results) == 0

def test_search_assets_limit_bounds(db):
    """Test that the limit parameter is bounded."""
    # Add >100 dummy assets
    for i in range(150):
        db.add_or_update_asset({"symbol": f"DUMMY{i}", "name": "Dummy", "asset_type": "stock"})

    # Requesting limit=1000 should return at most 100 (due to safe_limit bounds)
    results = db.search_assets("DUMMY", limit=1000)
    assert len(results) == 100

    # Requesting limit=0 or negative should return at least 1 (due to max(1, limit))
    results_negative = db.search_assets("DUMMY", limit=-5)
    assert len(results_negative) == 1

def test_search_assets_empty_query(db):
    """Test that empty queries return empty lists."""
    assert db.search_assets("") == []
    assert db.search_assets(None) == []
