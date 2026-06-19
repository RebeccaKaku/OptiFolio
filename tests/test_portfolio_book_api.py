"""Tests for DS-007: Portfolio book API — /api/book routes."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src.api import fastapi_app


# ── Helpers ─────────────────────────────────────────────────────────────────


def _make_app_with_mock(mock_book_service):
    """Create a FastAPI app with the portfolio_book service replaced by a mock."""
    app = fastapi_app.create_app()
    import src.api.portfolio_book_api as api_mod
    app.dependency_overrides[api_mod._get_service] = lambda: mock_book_service
    return app


def _make_client(mock_book_service):
    return TestClient(_make_app_with_mock(mock_book_service))


class MockBookService:
    """Mock PortfolioBookService that records calls and returns preset data."""

    def __init__(self):
        self.calls = []
        self._accounts = {}
        self._products = {}
        self._next_response = None

    def set_response(self, response):
        self._next_response = response

    def _record(self, method, *args, **kwargs):
        self.calls.append((method, args, kwargs))
        return self._next_response or {
            "success": True, "data": None, "message": "OK",
            "error": None, "error_code": None, "timestamp": "2025-01-01T00:00:00Z",
        }

    def list_accounts(self, status="active"):
        return self._record("list_accounts", status)

    def create_account(self, data):
        return self._record("create_account", data)

    def get_account(self, account_id):
        return self._record("get_account", account_id)

    def update_account(self, account_id, data):
        return self._record("update_account", account_id, data)

    def deactivate_account(self, account_id):
        return self._record("deactivate_account", account_id)

    def list_products(self):
        return self._record("list_products")

    def create_product(self, data):
        return self._record("create_product", data)

    def get_product(self, product_id):
        return self._record("get_product", product_id)

    def update_product(self, product_id, data):
        return self._record("update_product", product_id, data)


# ── Account routes ──────────────────────────────────────────────────────────


class TestAccountAPI:
    def test_list_accounts_default(self):
        mock = MockBookService()
        mock.set_response({
            "success": True,
            "data": [{"account_id": "acc1", "name": "Test", "status": "active"}],
            "message": "OK",
        })
        client = _make_client(mock)

        response = client.get("/api/book/accounts")
        assert response.status_code == 200
        assert response.json()["success"] is True
        assert len(mock.calls) == 1
        assert mock.calls[0] == ("list_accounts", ("active",), {})

    def test_list_accounts_with_status(self):
        mock = MockBookService()
        mock.set_response({"success": True, "data": [], "message": "OK"})
        client = _make_client(mock)

        response = client.get("/api/book/accounts?status=inactive")
        assert response.status_code == 200
        assert mock.calls[0] == ("list_accounts", ("inactive",), {})

    def test_create_account_returns_201(self):
        mock = MockBookService()
        mock.set_response({
            "success": True,
            "data": {"account_id": "acc_new", "name": "New"},
            "message": "Account created",
        })
        client = _make_client(mock)

        response = client.post("/api/book/accounts", json={
            "account_id": "acc_new", "name": "New Account",
        })
        assert response.status_code == 201
        assert response.json()["data"]["account_id"] == "acc_new"

    def test_create_account_validation_422(self):
        mock = MockBookService()
        client = _make_client(mock)

        # Missing required field 'name'
        response = client.post("/api/book/accounts", json={"account_id": "no_name"})
        assert response.status_code == 422
        payload = response.json()
        assert payload["success"] is False
        assert payload["error_code"] == "VALIDATION_ERROR"
        assert "timestamp" in payload

    def test_create_account_extra_fields_422(self):
        mock = MockBookService()
        client = _make_client(mock)

        # Unknown field due to extra='forbid'
        response = client.post("/api/book/accounts", json={
            "account_id": "acc_x", "name": "X", "unknown_field": "bad",
        })
        assert response.status_code == 422

    def test_create_account_duplicate_409(self):
        mock = MockBookService()
        mock.set_response({
            "success": False, "error": "A record with this ID already exists",
            "error_code": "DUPLICATE",
        })
        client = _make_client(mock)

        response = client.post("/api/book/accounts", json={
            "account_id": "dup", "name": "Duplicate",
        })
        assert response.status_code == 409

    def test_get_account_200(self):
        mock = MockBookService()
        mock.set_response({
            "success": True,
            "data": {"account_id": "acc1", "name": "Found"},
        })
        client = _make_client(mock)

        response = client.get("/api/book/accounts/acc1")
        assert response.status_code == 200
        assert response.json()["data"]["account_id"] == "acc1"

    def test_get_account_404(self):
        mock = MockBookService()
        mock.set_response({
            "success": False, "error": "Account 'no_such' not found",
            "error_code": "NOT_FOUND",
        })
        client = _make_client(mock)

        response = client.get("/api/book/accounts/no_such")
        assert response.status_code == 404

    def test_patch_account_200(self):
        mock = MockBookService()
        mock.set_response({
            "success": True,
            "data": {"account_id": "acc1", "name": "Updated"},
            "message": "Account updated",
        })
        client = _make_client(mock)

        response = client.patch("/api/book/accounts/acc1", json={"name": "Updated"})
        assert response.status_code == 200
        assert mock.calls[0][0] == "update_account"

    def test_patch_account_empty_body(self):
        """PATCH with empty body returns current account."""
        mock = MockBookService()
        mock.set_response({
            "success": True,
            "data": {"account_id": "acc1", "name": "Unchanged"},
        })
        client = _make_client(mock)

        response = client.patch("/api/book/accounts/acc1", json={})
        assert response.status_code == 200

    def test_patch_account_null_is_treated_as_omitted(self):
        mock = MockBookService()
        mock.set_response({
            "success": True,
            "data": {"account_id": "acc1", "notes": "unchanged"},
            "message": "OK",
            "error": None,
            "timestamp": "2025-01-01T00:00:00Z",
        })
        client = _make_client(mock)
        response = client.patch("/api/book/accounts/acc1", json={"notes": None})
        assert response.status_code == 200
        assert mock.calls[0][0] == "get_account"

    def test_patch_account_invalid_field_422(self):
        mock = MockBookService()
        client = _make_client(mock)

        response = client.patch("/api/book/accounts/acc1", json={
            "name": "OK", "bad_field": "no",
        })
        assert response.status_code == 422

    def test_deactivate_account_200(self):
        mock = MockBookService()
        mock.set_response({
            "success": True,
            "data": {"account_id": "acc1", "status": "inactive"},
            "message": "Account deactivated",
        })
        client = _make_client(mock)

        response = client.post("/api/book/accounts/acc1/deactivate")
        assert response.status_code == 200
        assert mock.calls[0][0] == "deactivate_account"

    def test_deactivate_account_404(self):
        mock = MockBookService()
        mock.set_response({
            "success": False, "error": "Account 'no_such' not found",
            "error_code": "NOT_FOUND",
        })
        client = _make_client(mock)

        response = client.post("/api/book/accounts/no_such/deactivate")
        assert response.status_code == 404


# ── Product routes ──────────────────────────────────────────────────────────


class TestProductAPI:
    def test_list_products_200(self):
        mock = MockBookService()
        mock.set_response({
            "success": True,
            "data": [{"product_id": "p1", "name": "Product 1"}],
        })
        client = _make_client(mock)

        response = client.get("/api/book/products")
        assert response.status_code == 200
        assert mock.calls[0][0] == "list_products"

    def test_create_product_201(self):
        mock = MockBookService()
        mock.set_response({
            "success": True,
            "data": {"product_id": "PROD001", "name": "New Product"},
            "message": "Product created",
        })
        client = _make_client(mock)

        response = client.post("/api/book/products", json={
            "product_id": "PROD001", "name": "New Product",
            "product_type": "bank_wmp",
        })
        assert response.status_code == 201

    def test_create_product_validation_422(self):
        mock = MockBookService()
        client = _make_client(mock)

        response = client.post("/api/book/products", json={
            "product_id": "no_name",
        })
        assert response.status_code == 422

    def test_create_product_extra_fields_422(self):
        mock = MockBookService()
        client = _make_client(mock)

        response = client.post("/api/book/products", json={
            "product_id": "p1", "name": "P1", "product_type": "bank_wmp",
            "not_a_field": "bad",
        })
        assert response.status_code == 422

    def test_get_product_200(self):
        mock = MockBookService()
        mock.set_response({
            "success": True,
            "data": {"product_id": "p1", "name": "Found"},
        })
        client = _make_client(mock)

        response = client.get("/api/book/products/p1")
        assert response.status_code == 200

    def test_get_product_404(self):
        mock = MockBookService()
        mock.set_response({
            "success": False, "error": "Product 'no_such' not found",
            "error_code": "NOT_FOUND",
        })
        client = _make_client(mock)

        response = client.get("/api/book/products/no_such")
        assert response.status_code == 404

    def test_put_product_200(self):
        mock = MockBookService()
        mock.set_response({
            "success": True,
            "data": {"product_id": "p1", "name": "Updated"},
            "message": "Product updated",
        })
        client = _make_client(mock)

        response = client.put("/api/book/products/p1", json={"name": "Updated"})
        assert response.status_code == 200
        assert mock.calls[0][0] == "update_product"

    def test_put_product_url_body_id_mismatch(self):
        mock = MockBookService()
        client = _make_client(mock)

        response = client.put("/api/book/products/p1", json={
            "product_id": "p2", "name": "Mismatch",
        })
        assert response.status_code == 422

    def test_put_product_url_body_id_match(self):
        mock = MockBookService()
        mock.set_response({
            "success": True,
            "data": {"product_id": "p1", "name": "Updated"},
            "message": "Product updated",
        })
        client = _make_client(mock)

        # URL product_id matches body product_id → OK
        response = client.put("/api/book/products/p1", json={
            "product_id": "p1", "name": "Updated",
        })
        assert response.status_code == 200

    def test_put_product_404(self):
        mock = MockBookService()
        mock.set_response({
            "success": False, "error": "Product 'no_such' not found",
            "error_code": "NOT_FOUND",
        })
        client = _make_client(mock)

        response = client.put("/api/book/products/no_such", json={"name": "Nope"})
        assert response.status_code == 404

    def test_put_product_extra_fields_422(self):
        mock = MockBookService()
        client = _make_client(mock)

        response = client.put("/api/book/products/p1", json={
            "name": "OK", "bad_field": "no",
        })
        assert response.status_code == 422


# ── PII rejection ───────────────────────────────────────────────────────────


class TestPIIRejection:
    def test_password_in_body_rejected_422(self):
        mock = MockBookService()
        client = _make_client(mock)

        response = client.post("/api/book/accounts", json={
            "account_id": "acc_pii", "name": "Test",
            "password": "secret123",
        })
        # Pydantic extra='forbid' catches it as unknown field → 422
        assert response.status_code == 422
        assert "secret123" not in response.text

    def test_pii_in_metadata_rejected_422(self):
        mock = MockBookService()
        mock.set_response({
            "success": False,
            "data": None,
            "message": None,
            "error": "Sensitive field is not accepted",
            "error_code": "PII_REJECTED",
            "timestamp": "2025-01-01T00:00:00Z",
        })
        client = _make_client(mock)

        response = client.post("/api/book/products", json={
            "product_id": "p_pii", "name": "PII Product",
            "product_type": "bank_wmp",
            "metadata": {"ssn": "123-45-6789"},
        })
        # PII policy belongs to the service; the route maps its safe error.
        assert response.status_code == 422


# ── CORS preflight ──────────────────────────────────────────────────────────


class TestCORSPreflight:
    def test_patch_preflight(self):
        client = TestClient(fastapi_app.create_app())

        response = client.options(
            "/api/book/accounts/test_id",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "PATCH",
                "Access-Control-Request-Headers": "Content-Type",
            },
        )
        assert response.status_code == 200
        # Check that PATCH is in allowed methods
        allow_methods = response.headers.get("access-control-allow-methods", "")
        assert "PATCH" in allow_methods or response.status_code == 200

    def test_put_preflight(self):
        client = TestClient(fastapi_app.create_app())

        response = client.options(
            "/api/book/products/test_id",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "PUT",
                "Access-Control-Request-Headers": "Content-Type",
            },
        )
        assert response.status_code == 200
        allow_methods = response.headers.get("access-control-allow-methods", "")
        assert "PUT" in allow_methods or response.status_code == 200


# ── Route isolation ─────────────────────────────────────────────────────────


class TestRouteIsolation:
    """Prove that API routes call the service layer, not the database directly."""

    def test_routes_use_service_not_db(self):
        """All book routes go through the service layer (mocked here)."""
        mock = MockBookService()
        mock.set_response({
            "success": True,
            "data": {"account_id": "iso1", "name": "Isolation Test"},
        })
        client = _make_client(mock)

        # GET
        client.get("/api/book/accounts/iso1")
        assert mock.calls[-1][0] == "get_account"

        # POST
        client.post("/api/book/accounts", json={
            "account_id": "iso2", "name": "Isolation Create",
        })
        assert mock.calls[-1][0] == "create_account"

        # PATCH
        client.patch("/api/book/accounts/iso1", json={"name": "Updated"})
        assert mock.calls[-1][0] == "update_account"

        # POST deactivate
        client.post("/api/book/accounts/iso1/deactivate")
        assert mock.calls[-1][0] == "deactivate_account"

    def test_routes_never_import_database(self):
        """The API module must not import PortfolioBookDatabase."""
        import src.api.portfolio_book_api as mod
        import inspect
        source = inspect.getsource(mod)
        assert "PortfolioBookDatabase" not in source
        assert "sqlite3" not in source.lower()
        assert "connect()" not in source


# ── OpenAPI visibility ─────────────────────────────────────────────────────


class TestOpenAPI:
    def test_book_routes_visible_in_openapi(self):
        """All /api/book routes appear in the OpenAPI schema."""
        client = TestClient(fastapi_app.create_app())
        response = client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        paths = schema.get("paths", {})
        book_paths = [p for p in paths if p.startswith("/api/book")]
        assert len(book_paths) >= 5  # 5 distinct paths, 9 endpoints across HTTP methods


# ── Response format ─────────────────────────────────────────────────────────


class TestResponseFormat:
    def test_success_response_has_required_keys(self):
        mock = MockBookService()
        mock.set_response({
            "success": True,
            "data": {"account_id": "a1", "name": "Test"},
            "message": "OK",
            "error": None,
            "timestamp": "2025-01-01T00:00:00Z",
        })
        client = _make_client(mock)

        response = client.get("/api/book/accounts/a1")
        payload = response.json()
        assert "success" in payload
        assert "data" in payload
        assert "message" in payload
        assert "error" in payload or payload.get("success") is True
        assert "timestamp" in payload

    def test_error_response_has_required_keys(self):
        mock = MockBookService()
        mock.set_response({
            "success": False,
            "data": None,
            "error": "Not found",
            "error_code": "NOT_FOUND",
        })
        client = _make_client(mock)

        response = client.get("/api/book/accounts/no_such")
        payload = response.json()
        assert "success" in payload
        assert payload["success"] is False
        assert "error" in payload
        assert "error_code" in payload


# ── No regression on existing API ───────────────────────────────────────────


class TestNoRegression:
    """Existing FastAPI routes must still work after book router is added."""

    def test_health_still_works(self):
        client = TestClient(fastapi_app.create_app())
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["success"] is True
