"""Lazy application service graph."""

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict

from src.analytics.alerts import AlertEngine

from .research_service import ResearchService
from .system_service import SystemService


class IngestionService:
    """Stub for ingestion metadata API."""
    def get_runs(self) -> Dict[str, Any]:
        from src.services.response import success
        return success({"records": []}, "Ingestion pipeline not yet wired")


@dataclass(frozen=True)
class ApplicationServices:
    system: SystemService
    research: ResearchService
    ingestion: IngestionService
    alerts: AlertEngine              # risk alert checks
    portfolio_book: "PortfolioBookService"  # DS-007 — personal book CRUD
    book_valuation: "BookValuationService"  # DS-012
    my_money: "MyMoneyService"              # DS-015
    portfolio: "PortfolioService"      # date-aware valuation
    decision_journal: "DecisionJournalService"  # DS-024


@lru_cache(maxsize=1)
def get_application_services() -> ApplicationServices:
    from src.core.portfolio_book_db import PortfolioBookDatabase
    from src.services.portfolio_book_service import PortfolioBookService
    from src.services.book_valuation_service import BookValuationService
    from src.services.my_money_service import MyMoneyService
    from src.services.portfolio_service import PortfolioService
    from src.services.decision_journal_service import DecisionJournalService
    from findata.serving.provider import DataProvider

    portfolio_book_db = PortfolioBookDatabase()
    portfolio_book_db.initialize()

    data_provider = DataProvider()
    book_val_svc = BookValuationService(portfolio_book_db, data_provider)
    return ApplicationServices(
        system=SystemService(),
        research=ResearchService(),
        ingestion=IngestionService(),
        alerts=AlertEngine(),
        portfolio_book=PortfolioBookService(portfolio_book_db, data_provider),
        book_valuation=book_val_svc,
        my_money=MyMoneyService(portfolio_book_db, book_val_svc, data_provider),
        portfolio=PortfolioService(),
        decision_journal=DecisionJournalService(portfolio_book_db),
    )
