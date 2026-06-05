import pytest
import pandas as pd
from datetime import datetime
from FinData.store.ingestion_log import IngestionLog, IngestionRun

def test_ingestion_run_creation():
    run = IngestionRun.create("yahoo", "AAPL")
    assert run.provider == "yahoo"
    assert run.asset_id == "AAPL"
    assert run.status == "started"
    assert isinstance(run.started_at, datetime)
    assert run.run_id is not None

def test_ingestion_log_save_load(tmp_path):
    log_file = tmp_path / "test_log.parquet"
    log = IngestionLog(log_path=log_file)

    run = IngestionRun.create("yahoo", "AAPL")
    log.log_run(run)

    runs = log.get_runs()
    assert len(runs) == 1
    assert runs[0].run_id == run.run_id
    assert runs[0].status == "started"

    # Update run
    run.status = "success"
    run.finished_at = datetime.now()
    log.log_run(run)

    runs = log.get_runs()
    assert len(runs) == 1
    assert runs[0].status == "success"
