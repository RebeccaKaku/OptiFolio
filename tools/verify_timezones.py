import pandas as pd
from findata.store.schemas import infer_market_timezone, normalize_market_frame

def test_inference():
    test_cases = [
        ("US_EQ:AAPL", "America/New_York"),
        ("US_ETF:SPY", "America/New_York"),
        ("CN_STOCK:600519", "Asia/Shanghai"),
        ("CN_FUND:510300", "Asia/Shanghai"),
        ("HK_EQ:0700", "Asia/Hong_Kong"),
        ("FX:USDCNY", "UTC"),
        ("CRYPTO:BTC", "UTC"),
        ("600519", "Asia/Shanghai"),
        ("AAPL", "America/New_York"),
        ("BRK.B", "America/New_York"),
        ("USDCNY", "UTC"),
        ("HK_9988", "Asia/Hong_Kong"),
        ("CN_TEST", "Asia/Shanghai"),
    ]

    for aid, expected in test_cases:
        actual = infer_market_timezone(aid)
        print(f"Asset: {aid:20} Expected: {expected:20} Actual: {actual:20} {'PASS' if actual == expected else 'FAIL'}")

def test_normalization():
    df = pd.DataFrame({
        "date": ["2024-01-08 21:00:00+00:00"],
        "close": [100.0]
    })

    # Test US_EQ
    norm_us = normalize_market_frame(df, asset_id="US_EQ:AAPL")
    print(f"US_EQ:AAPL timezone: {norm_us['timezone'].iloc[0]} date: {norm_us['date'].iloc[0]}")
    # 21:00 UTC is 16:00 EST (Jan 8)

    # Test CN_STOCK
    norm_cn = normalize_market_frame(df, asset_id="CN_STOCK:600519")
    print(f"CN_STOCK:600519 timezone: {norm_cn['timezone'].iloc[0]} date: {norm_cn['date'].iloc[0]}")
    # 21:00 UTC is 05:00 CST (Jan 9)

if __name__ == "__main__":
    print("--- Timezone Inference ---")
    test_inference()
    print("\n--- Normalization ---")
    test_normalization()
