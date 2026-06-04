import pandas as pd

from src.data_foundation import MarketDataRepository, normalize_market_frame


def test_normalize_market_frame_accepts_provider_columns():
    raw = pd.DataFrame(
        {
            "Date": ["2024-01-01", "2024-01-02"],
            "Close": [100, 101],
            "Volume": [1000, 1100],
        }
    )

    normalized = normalize_market_frame(raw, asset_id="AAA", source="unit", currency="USD")

    assert list(normalized["asset_id"].unique()) == ["AAA"]
    assert list(normalized["adj_close"]) == [100, 101]
    assert normalized["source"].eq("unit").all()


def test_market_data_repository_saves_and_queries_price_matrix(tmp_path):
    repo = MarketDataRepository(tmp_path)
    repo.save_canonical(
        pd.DataFrame(
            {
                "date": ["2024-01-01", "2024-01-02", "2024-01-03"],
                "close": [100, 102, 101],
            }
        ),
        asset_id="AAA",
        source="unit",
        currency="USD",
    )
    repo.save_canonical(
        pd.DataFrame(
            {
                "date": ["2024-01-01", "2024-01-02", "2024-01-03"],
                "close": [50, 51, 52],
            }
        ),
        asset_id="BBB",
        source="unit",
        currency="USD",
    )

    prices = repo.get_prices(["AAA", "BBB"], start="2024-01-02")
    returns = repo.get_returns(["AAA", "BBB"])
    report = repo.missing_report(["AAA", "BBB"])

    assert list(prices.columns) == ["AAA", "BBB"]
    assert prices.shape == (2, 2)
    assert returns.shape == (2, 2)
    assert report["missing"].sum() == 0


def test_market_data_repository_saves_bronze(tmp_path):
    repo = MarketDataRepository(tmp_path)
    df = pd.DataFrame(
        {
            "close": [100, 101],
        },
        index=pd.to_datetime(["2024-01-01", "2024-01-02"]),
    )
    df.index.name = "timestamp"

    # Save to bronze
    path = repo.save_bronze(df, asset_id="TEST", provider="test_provider", ingest_date="2024-05-22")

    assert path.exists()
    assert "bronze" in str(path)
    assert "provider=test_provider" in str(path)
    assert "TEST.parquet" in str(path)

    # Verify content
    loaded = pd.read_parquet(path)
    assert loaded.shape == (2, 1)
    assert list(loaded["close"]) == [100, 101]
