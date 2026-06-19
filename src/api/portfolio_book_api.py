"""Portfolio book API — /api/book routes for accounts and products.

Uses an independent ``APIRouter`` with Pydantic request models
(``extra='forbid'``).  No SQL, database connections, or financial
validation lives here — all business logic is delegated to
``PortfolioBookService``.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field

from src.services.response import failure

# ── Router ──────────────────────────────────────────────────────────────────

class BookRoute(APIRoute):
    """Normalize request validation errors without echoing submitted values."""

    def get_route_handler(self):
        original_handler = super().get_route_handler()

        async def handler(request: Request):
            try:
                return await original_handler(request)
            except RequestValidationError as exc:
                safe_errors = [
                    {
                        "location": list(error.get("loc", ())),
                        "type": error.get("type", "validation_error"),
                        "message": error.get("msg", "Invalid value"),
                    }
                    for error in exc.errors()
                ]
                return _json_response(
                    failure(
                        "Request validation failed",
                        error_code="VALIDATION_ERROR",
                        details={"errors": safe_errors},
                    ),
                    status_override=422,
                )

        return handler


router = APIRouter(
    prefix="/api/book", tags=["portfolio book"], route_class=BookRoute
)


# ── Pydantic models ─────────────────────────────────────────────────────────


if hasattr(BaseModel, "model_fields"):  # Pydantic v2
    class StrictRequestModel(BaseModel):
        model_config = {"extra": "forbid"}
else:  # pragma: no cover - exercised only with Pydantic v1
    class StrictRequestModel(BaseModel):
        class Config:
            extra = "forbid"


def _model_dump(model: BaseModel, **kwargs) -> Dict[str, Any]:
    """Support both Pydantic v1 and v2 without changing the API contract."""
    if hasattr(model, "model_dump"):
        return model.model_dump(**kwargs)
    return model.dict(**kwargs)


class AccountCreateRequest(StrictRequestModel):
    account_id: str = Field(min_length=1, description="Unique account identifier")
    name: str = Field(min_length=1, description="Human-readable account name")
    institution: str = Field(default="", description="Financial institution name")
    account_type: str = Field(default="brokerage", description="Account type")
    base_currency: str = Field(default="CNY", description="3-letter ISO 4217 currency code")
    ownership_scope: str = Field(default="personal", description="personal | joint")
    notes: str = Field(default="", description="Free-form notes")


class AccountUpdateRequest(StrictRequestModel):
    name: Optional[str] = Field(default=None, min_length=1, description="Human-readable account name")
    institution: Optional[str] = Field(default=None, description="Financial institution name")
    account_type: Optional[str] = Field(default=None, description="Account type")
    base_currency: Optional[str] = Field(default=None, min_length=3, max_length=3, description="3-letter ISO 4217 currency code")
    ownership_scope: Optional[str] = Field(default=None, description="personal | joint")
    notes: Optional[str] = Field(default=None, description="Free-form notes")

    def update_dict(self) -> Dict[str, Any]:
        """Return only the fields that were explicitly set (non-None)."""
        return _model_dump(self, exclude_unset=True, exclude_none=True)


class ProductCreateRequest(StrictRequestModel):
    product_id: str = Field(min_length=1, description="Unique product identifier")
    name: str = Field(min_length=1, description="Human-readable product name")
    product_type: str = Field(min_length=1, description="Product type")
    issuer: Optional[str] = Field(default=None, description="Issuer name")
    manager: Optional[str] = Field(default=None, description="Fund manager name")
    currency: str = Field(default="CNY", description="3-letter ISO 4217 currency code")
    risk_level: Optional[str] = Field(default=None, description="Risk level label")
    liquidity_type: Optional[str] = Field(default=None, description="Liquidity classification")
    fee_policy_id: Optional[str] = Field(default=None, description="Fee policy reference")
    benchmark_id: Optional[str] = Field(default=None, description="Benchmark reference")
    primary_instrument_id: Optional[str] = Field(default=None, description="Primary instrument reference")
    data_source: str = Field(default="manual", description="Data provenance")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Extension key-value pairs")


class ProductUpdateRequest(StrictRequestModel):
    product_id: Optional[str] = Field(default=None, description="Must match URL path product_id")
    name: Optional[str] = Field(default=None, min_length=1)
    product_type: Optional[str] = Field(default=None, min_length=1)
    issuer: Optional[str] = Field(default=None)
    manager: Optional[str] = Field(default=None)
    currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    risk_level: Optional[str] = Field(default=None)
    liquidity_type: Optional[str] = Field(default=None)
    fee_policy_id: Optional[str] = Field(default=None)
    benchmark_id: Optional[str] = Field(default=None)
    primary_instrument_id: Optional[str] = Field(default=None)
    data_source: Optional[str] = Field(default=None)
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Extension key-value pairs")

    def update_dict(self) -> Dict[str, Any]:
        """Return only the fields that were explicitly set (non-None)."""
        return _model_dump(self, exclude_unset=True, exclude_none=True)


class SnapshotBatchCreateRequest(StrictRequestModel):
    batch_id: str = Field(min_length=1)
    as_of: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    source: str = Field(default="manual")
    quality: str = Field(default="reported")
    notes: Optional[str] = Field(default=None)


class AccountCoverageUpdateRequest(StrictRequestModel):
    coverage: str = Field(pattern="^(complete|partial|empty)$")
    notes: Optional[str] = Field(default=None)


class PositionSnapshotCreateRequest(StrictRequestModel):
    account_id: str = Field(min_length=1)
    product_id: str = Field(min_length=1)
    quantity: Optional[float] = Field(default=None)
    market_value: Optional[float] = Field(default=None)
    cost_basis: Optional[float] = Field(default=None)
    currency: str = Field(default="CNY", min_length=3, max_length=3)
    source: Optional[str] = Field(default=None)
    quality: Optional[str] = Field(default=None)
    notes: Optional[str] = Field(default=None)


# ── Status code mapping ─────────────────────────────────────────────────────

_ERROR_CODE_STATUS = {
    "NOT_FOUND": 404,
    "DUPLICATE": 409,
    "ALREADY_CONFIRMED": 409,
    "VALIDATION_ERROR": 422,
    "PII_REJECTED": 422,
    "FOREIGN_KEY_ERROR": 422,
    "DATABASE_ERROR": 500,
    "INTERNAL_ERROR": 500,
}


def _json_response(payload: Dict[str, Any], status_override: Optional[int] = None) -> JSONResponse:
    """Map service response dict to an HTTP status code."""
    if status_override is not None:
        status_code = status_override
    elif payload.get("success", True):
        status_code = 200
    else:
        error_code = payload.get("error_code", "")
        status_code = _ERROR_CODE_STATUS.get(error_code, 400)
    return JSONResponse(status_code=status_code, content=jsonable_encoder(payload))


# ── Dependency ──────────────────────────────────────────────────────────────

def _get_service():
    """Lazy-import the book service from the application service graph."""
    from src.services.application import get_application_services
    return get_application_services().portfolio_book


# ── Account routes ──────────────────────────────────────────────────────────


@router.get("/accounts")
def list_accounts(status: str = "active", svc=Depends(_get_service)):
    """List accounts, optionally filtered by status (active | inactive | all)."""
    result = svc.list_accounts(status)
    return _json_response(result)


@router.post("/accounts")
def create_account(payload: AccountCreateRequest, svc=Depends(_get_service)):
    """Create a new account."""
    data = _model_dump(payload)
    result = svc.create_account(data)
    status_code = 201 if result.get("success") else None
    return _json_response(result, status_override=status_code)


@router.get("/accounts/{account_id}")
def get_account(account_id: str, svc=Depends(_get_service)):
    """Get a single account by ID."""
    result = svc.get_account(account_id)
    status_code = None
    if not result.get("success") and result.get("error_code") == "NOT_FOUND":
        status_code = 404
    return _json_response(result, status_override=status_code)


# ── Snapshot routes ─────────────────────────────────────────────────────────


@router.post("/snapshot-batches")
def create_snapshot_batch(payload: SnapshotBatchCreateRequest, svc=Depends(_get_service)):
    """Create a new snapshot batch (draft)."""
    result = svc.create_snapshot_batch(_model_dump(payload))
    status_code = 201 if result.get("success") else None
    return _json_response(result, status_override=status_code)


@router.get("/snapshot-batches/{batch_id}")
def get_snapshot_batch(batch_id: str, svc=Depends(_get_service)):
    """Get batch details, positions, and progress."""
    result = svc.get_snapshot_batch(batch_id)
    return _json_response(result)


@router.put("/snapshot-batches/{batch_id}/accounts/{account_id}/coverage")
def set_batch_account_coverage(
    batch_id: str,
    account_id: str,
    payload: AccountCoverageUpdateRequest,
    svc=Depends(_get_service),
):
    """Set coverage (complete|partial|empty) for an account in a batch."""
    result = svc.set_batch_account_coverage(batch_id, account_id, _model_dump(payload))
    return _json_response(result)


@router.post("/snapshot-batches/{batch_id}/positions")
def add_snapshot_position(
    batch_id: str, payload: PositionSnapshotCreateRequest, svc=Depends(_get_service)
):
    """Add a position to a draft batch."""
    result = svc.add_snapshot_position(batch_id, _model_dump(payload))
    status_code = 201 if result.get("success") else None
    return _json_response(result, status_override=status_code)


@router.post("/snapshot-batches/{batch_id}/validate")
def validate_snapshot_batch(batch_id: str, svc=Depends(_get_service)):
    """Validate if a batch is confirmable."""
    result = svc.validate_snapshot_batch(batch_id)
    return _json_response(result)


@router.post("/snapshot-batches/{batch_id}/confirm")
def confirm_snapshot_batch(batch_id: str, svc=Depends(_get_service)):
    """Confirm a snapshot batch (makes it immutable)."""
    result = svc.confirm_snapshot_batch(batch_id)
    return _json_response(result)


@router.patch("/accounts/{account_id}")
def update_account(account_id: str, payload: AccountUpdateRequest, svc=Depends(_get_service)):
    """Update fields on an existing account (partial update)."""
    data = payload.update_dict()
    if not data:
        # No fields to update — return current account
        result = svc.get_account(account_id)
        if not result.get("success"):
            return _json_response(result)
        return _json_response(result)
    result = svc.update_account(account_id, data)
    status_code = None
    if not result.get("success") and result.get("error_code") == "NOT_FOUND":
        status_code = 404
    return _json_response(result, status_override=status_code)


@router.post("/accounts/{account_id}/deactivate")
def deactivate_account(account_id: str, svc=Depends(_get_service)):
    """Deactivate (soft-delete) an account."""
    result = svc.deactivate_account(account_id)
    status_code = None
    if not result.get("success") and result.get("error_code") == "NOT_FOUND":
        status_code = 404
    return _json_response(result, status_override=status_code)


# ── Product routes ──────────────────────────────────────────────────────────


@router.get("/products")
def list_products(svc=Depends(_get_service)):
    """List all products."""
    result = svc.list_products()
    return _json_response(result)


@router.post("/products")
def create_product(payload: ProductCreateRequest, svc=Depends(_get_service)):
    """Create a new product."""
    data = _model_dump(payload)
    result = svc.create_product(data)
    status_code = 201 if result.get("success") else None
    return _json_response(result, status_override=status_code)


@router.get("/products/{product_id}")
def get_product(product_id: str, svc=Depends(_get_service)):
    """Get a single product by ID."""
    result = svc.get_product(product_id)
    status_code = None
    if not result.get("success") and result.get("error_code") == "NOT_FOUND":
        status_code = 404
    return _json_response(result, status_override=status_code)


@router.put("/products/{product_id}")
def update_product(product_id: str, payload: ProductUpdateRequest, svc=Depends(_get_service)):
    """Replace/update an existing product."""
    data = payload.update_dict()

    # URL ID must match body ID if body ID is present
    body_id = data.pop("product_id", None)
    if body_id is not None and body_id != product_id:
        return _json_response(
            failure(
                f"URL product_id {product_id!r} does not match body product_id {body_id!r}",
                error_code="VALIDATION_ERROR",
            ),
            status_override=422,
        )
    result = svc.update_product(product_id, data)
    status_code = None
    if not result.get("success") and result.get("error_code") == "NOT_FOUND":
        status_code = 404
    return _json_response(result, status_override=status_code)
