"""
Tests for Cloudflare R2 / S3 Object Storage integration.
Validates:
1. Configuration detection and credential masking
2. Storage upload, download, and delete operations via mocked boto3 client
3. Fallback and error handling for missing objects (NoSuchKey -> FileNotFoundError -> 404)
4. Strict production mode validation (prohibits unconfigured R2 in production)
5. End-to-end API upload and download flow when R2 is enabled
"""

import io
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_database
from app.core.config import Settings
from app.core.object_storage import (
    delete_from_r2,
    download_from_r2,
    get_r2_client,
    upload_to_r2,
)
from app.main import app
from app.models.user import UserResponse, UserRole
from datetime import datetime, timezone


def _make_user(
    user_id: str = "user-r2-test",
    email: str = "r2owner@example.com",
    role: UserRole = UserRole.OWNER,
) -> UserResponse:
    return UserResponse(
        id=user_id,
        email=email,
        full_name="R2 Test User",
        role=role,
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )


PDF_BYTES = b"%PDF-1.4 sample pdf content for r2 test"


class TestR2Configuration:
    """Test configuration fields, property detection, and secret masking."""

    def test_is_r2_configured_false_by_default(self):
        s = Settings(
            R2_ACCOUNT_ID="",
            R2_ACCESS_KEY_ID="",
            R2_SECRET_ACCESS_KEY="",
            R2_BUCKET_NAME="trustvault-documents",
        )
        assert s.is_r2_configured is False

    def test_is_r2_configured_true_when_credentials_provided(self):
        s = Settings(
            R2_ACCOUNT_ID="acc123",
            R2_ACCESS_KEY_ID="key123",
            R2_SECRET_ACCESS_KEY="secret123",
            R2_BUCKET_NAME="trustvault-documents",
        )
        assert s.is_r2_configured is True

    def test_r2_credentials_are_masked_in_get_safe_summary(self):
        s = Settings(
            SECRET_KEY="supersecretkey12345678901234567890",
            R2_ACCOUNT_ID="acc123",
            R2_ACCESS_KEY_ID="my-access-key",
            R2_SECRET_ACCESS_KEY="my-secret-key",
            R2_BUCKET_NAME="trustvault-documents",
        )
        summary = s.get_safe_summary()
        assert summary["R2_ACCESS_KEY_ID"] == "***MASKED***"
        assert summary["R2_SECRET_ACCESS_KEY"] == "***MASKED***"
        assert summary["SECRET_KEY"] == "***MASKED***"
        assert summary["R2_BUCKET_NAME"] == "trustvault-documents"


class TestR2StorageOperations:
    """Test object storage helper functions with mocked S3 client."""

    @pytest.mark.asyncio
    async def test_upload_to_r2_calls_put_object(self):
        mock_client = MagicMock()
        with patch("app.core.object_storage.settings") as mock_settings, \
             patch("app.core.object_storage.get_r2_client", return_value=mock_client):
            mock_settings.is_r2_configured = True
            mock_settings.R2_BUCKET_NAME = "trustvault-documents"

            await upload_to_r2("user-1/file.pdf", PDF_BYTES, "application/pdf")

            mock_client.put_object.assert_called_once_with(
                Bucket="trustvault-documents",
                Key="user-1/file.pdf",
                Body=PDF_BYTES,
                ContentType="application/pdf",
            )

    @pytest.mark.asyncio
    async def test_download_from_r2_calls_get_object(self):
        mock_client = MagicMock()
        mock_body = MagicMock()
        mock_body.read.return_value = PDF_BYTES
        mock_client.get_object.return_value = {"Body": mock_body}

        with patch("app.core.object_storage.settings") as mock_settings, \
             patch("app.core.object_storage.get_r2_client", return_value=mock_client):
            mock_settings.is_r2_configured = True
            mock_settings.R2_BUCKET_NAME = "trustvault-documents"

            result = await download_from_r2("user-1/file.pdf")

            assert result == PDF_BYTES
            mock_client.get_object.assert_called_once_with(
                Bucket="trustvault-documents",
                Key="user-1/file.pdf",
            )

    @pytest.mark.asyncio
    async def test_download_from_r2_raises_filenotfound_when_key_missing(self):
        mock_client = MagicMock()
        error_response = {"Error": {"Code": "NoSuchKey", "Message": "The specified key does not exist."}}
        mock_client.get_object.side_effect = ClientError(error_response, "GetObject")

        with patch("app.core.object_storage.settings") as mock_settings, \
             patch("app.core.object_storage.get_r2_client", return_value=mock_client):
            mock_settings.is_r2_configured = True
            mock_settings.R2_BUCKET_NAME = "trustvault-documents"

            with pytest.raises(FileNotFoundError):
                await download_from_r2("user-1/nonexistent.pdf")

    @pytest.mark.asyncio
    async def test_delete_from_r2_calls_delete_object(self):
        mock_client = MagicMock()
        with patch("app.core.object_storage.settings") as mock_settings, \
             patch("app.core.object_storage.get_r2_client", return_value=mock_client):
            mock_settings.is_r2_configured = True
            mock_settings.R2_BUCKET_NAME = "trustvault-documents"

            await delete_from_r2("user-1/file.pdf")

            mock_client.delete_object.assert_called_once_with(
                Bucket="trustvault-documents",
                Key="user-1/file.pdf",
            )

    @pytest.mark.asyncio
    async def test_production_fails_if_r2_not_configured(self):
        with patch("app.core.object_storage.settings") as mock_settings:
            mock_settings.is_r2_configured = False
            mock_settings.APP_ENV = "production"

            with pytest.raises(RuntimeError) as exc_info:
                await upload_to_r2("user-1/file.pdf", PDF_BYTES, "application/pdf")
            assert "Cloudflare R2" in str(exc_info.value)


class TestR2ApiEndpoints:
    """Test document endpoints when R2 is configured."""

    def test_upload_stores_r2_object_key_in_db(self, tmp_path):
        test_user = _make_user(user_id="user-r2-prod")
        records = []

        class MockDocsCol:
            async def insert_one(self, doc):
                records.append(dict(doc))
                res = MagicMock()
                res.inserted_id = doc.get("_id")
                return res

            async def count_documents(self, q):
                return len(records)

        class MockDb:
            def __getitem__(self, item):
                if item == "documents":
                    return MockDocsCol()
                return MagicMock()

        mock_db = MockDb()
        app.dependency_overrides[get_database] = lambda: mock_db
        app.dependency_overrides[get_current_user] = lambda: test_user

        try:
            with patch("app.api.v1.endpoints.documents.settings") as mock_settings, \
                 patch("app.api.v1.endpoints.documents.upload_to_r2", new_callable=AsyncMock) as mock_upload:
                mock_settings.is_r2_configured = True
                mock_settings.max_upload_size_bytes = 10 * 1024 * 1024
                mock_settings.MAX_UPLOAD_SIZE_MB = 10

                with TestClient(app) as client:
                    resp = client.post(
                        "/api/v1/documents/upload",
                        files={"file": ("contract.pdf", io.BytesIO(PDF_BYTES), "application/pdf")},
                    )

                assert resp.status_code == 201
                assert mock_upload.await_count == 1

                # Verify uploaded key starts with owner ID prefix and ends with .pdf
                called_key = mock_upload.await_args[0][0]
                assert called_key.startswith("user-r2-prod/")
                assert called_key.endswith(".pdf")

                # Verify MongoDB record contains the R2 key, NOT an absolute server filesystem path
                assert len(records) == 1
                assert records[0]["storage_path"] == called_key
                assert not records[0]["storage_path"].startswith("/")
                assert "opt/render" not in records[0]["storage_path"]
        finally:
            app.dependency_overrides.clear()

    def test_download_streams_from_r2(self):
        test_user = _make_user(user_id="user-r2-prod")
        doc_record = {
            "_id": "doc-r2-1",
            "id": "doc-r2-1",
            "filename": "my_document.pdf",
            "content_type": "application/pdf",
            "size_bytes": len(PDF_BYTES),
            "owner_id": test_user.id,
            "status": "active",
            "storage_path": "user-r2-prod/doc-uuid-123.pdf",
        }

        class MockCollection:
            async def find_one(self, q):
                if "$or" in q:
                    for branch in q["$or"]:
                        if branch.get("id") == "doc-r2-1" or branch.get("_id") == "doc-r2-1":
                            return doc_record
                elif q.get("id") == "doc-r2-1" or q.get("_id") == "doc-r2-1":
                    return doc_record
                return None

            async def insert_one(self, doc):
                res = MagicMock()
                res.inserted_id = "audit-1"
                return res

        class MockDb:
            def __getitem__(self, item):
                return MockCollection()

        mock_db = MockDb()
        app.dependency_overrides[get_database] = lambda: mock_db
        app.dependency_overrides[get_current_user] = lambda: test_user

        try:
            with patch("app.api.v1.endpoints.documents.settings") as mock_settings, \
                 patch("app.api.v1.endpoints.documents.download_from_r2", new_callable=AsyncMock, return_value=PDF_BYTES) as mock_dl:
                mock_settings.is_r2_configured = True

                with TestClient(app) as client:
                    resp = client.get("/api/v1/documents/doc-r2-1/download")

                assert resp.status_code == 200
                assert resp.content == PDF_BYTES
                assert resp.headers["content-type"] == "application/pdf"
                assert 'filename="my_document.pdf"' in resp.headers["content-disposition"]
                mock_dl.assert_awaited_once_with("user-r2-prod/doc-uuid-123.pdf")
        finally:
            app.dependency_overrides.clear()

    def test_mongodb_insert_failure_cleans_up_uploaded_r2_object(self):
        from pymongo.errors import PyMongoError
        test_user = _make_user(user_id="user-r2-prod")

        class BrokenDb:
            def __getitem__(self, item):
                col = MagicMock()
                col.insert_one = AsyncMock(side_effect=PyMongoError("DB connection lost"))
                return col

        app.dependency_overrides[get_database] = lambda: BrokenDb()
        app.dependency_overrides[get_current_user] = lambda: test_user
        try:
            with patch("app.api.v1.endpoints.documents.settings") as mock_settings, \
                 patch("app.api.v1.endpoints.documents.upload_to_r2", new_callable=AsyncMock) as mock_upload, \
                 patch("app.api.v1.endpoints.documents.delete_from_r2", new_callable=AsyncMock) as mock_delete:
                mock_settings.is_r2_configured = True
                mock_settings.max_upload_size_bytes = 10 * 1024 * 1024
                mock_settings.MAX_UPLOAD_SIZE_MB = 10

                with TestClient(app) as client:
                    resp = client.post(
                        "/api/v1/documents/upload",
                        files={"file": ("contract.pdf", io.BytesIO(PDF_BYTES), "application/pdf")},
                    )

                assert resp.status_code == 503
                assert mock_upload.await_count == 1
                assert mock_delete.await_count == 1
                uploaded_key = mock_upload.await_args[0][0]
                deleted_key = mock_delete.await_args[0][0]
                assert uploaded_key == deleted_key
        finally:
            app.dependency_overrides.clear()

    def test_authorization_checked_before_downloading_r2_bytes(self):
        owner_user = _make_user(user_id="owner-1")
        other_user = _make_user(user_id="other-attacker")
        doc_record = {
            "_id": "doc-secret-1",
            "id": "doc-secret-1",
            "filename": "secret.pdf",
            "content_type": "application/pdf",
            "size_bytes": len(PDF_BYTES),
            "owner_id": owner_user.id,
            "status": "active",
            "storage_path": "owner-1/secret.pdf",
        }

        class MockCol:
            async def find_one(self, q):
                if "$or" in q:
                    for branch in q["$or"]:
                        if branch.get("id") == "doc-secret-1" or branch.get("_id") == "doc-secret-1":
                            return doc_record
                return None

            async def insert_one(self, doc):
                return MagicMock()

        class MockDb:
            def __getitem__(self, item):
                return MockCol()

        app.dependency_overrides[get_database] = lambda: MockDb()
        app.dependency_overrides[get_current_user] = lambda: other_user

        try:
            with patch("app.api.v1.endpoints.documents.settings") as mock_settings, \
                 patch("app.api.v1.endpoints.documents.download_from_r2", new_callable=AsyncMock) as mock_dl:
                mock_settings.is_r2_configured = True
                with TestClient(app) as client:
                    resp = client.get("/api/v1/documents/doc-secret-1/download")

                assert resp.status_code == 403
                # Verify download_from_r2 was never called; no bytes were fetched
                assert mock_dl.await_count == 0
        finally:
            app.dependency_overrides.clear()


class TestProductionStartupSafety:
    """Test that production environment refuses to boot without persistent storage credentials."""

    @pytest.mark.asyncio
    async def test_production_startup_fails_safely_when_r2_missing(self):
        from app.main import lifespan
        with patch("app.main.settings") as mock_settings:
            mock_settings.APP_ENV = "production"
            mock_settings.is_r2_configured = False
            with pytest.raises(RuntimeError) as exc:
                async with lifespan(app):
                    pass
            assert "Cloudflare R2" in str(exc.value)

