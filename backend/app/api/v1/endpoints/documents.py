"""
Document management API endpoints for TrustVault.

Provides authenticated document upload and listing.
All endpoints require a valid Bearer JWT token.
File content is stored privately on the server filesystem;
storage paths are never returned in API responses.
"""

import io
import logging
import os
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Query, Response, status
from fastapi.responses import FileResponse
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.api.deps import get_current_user, get_database
from app.core.audit import record_audit_event
from app.core.authorization import (
    verify_document_owner,
    verify_document_read_access,
    verify_document_edit_access,
)
from app.core.config import settings
from app.core.file_validation import validate_file_content
from app.core.object_storage import (
    delete_from_r2,
    download_from_r2,
    is_r2_configured,
    upload_to_r2,
)
from app.models.audit import AuditAction, AuditOutcome
from app.models.document import (
    DocumentInDB,
    DocumentListResponse,
    DocumentResponse,
    DocumentStatus,
    DocumentUpdateRequest,
)
from app.models.permission import (
    PermissionGrantRequest,
    PermissionInDB,
    PermissionLevel,
    PermissionListResponse,
    PermissionResponse,
)
from app.models.user import UserResponse

logger = logging.getLogger("trustvault.api.documents")

router = APIRouter()

# ---------------------------------------------------------------------------
# Supported document formats: MIME type / filename extension -> format key
#
# The client-provided Content-Type is treated only as a CLAIM about the file.
# Every upload is additionally validated against the actual file bytes
# (magic numbers / archive structure / text rule) before storage.
# ---------------------------------------------------------------------------

# Canonical MIME type per validated format (used for metadata + allowlist)
MIME_TO_FORMAT: dict[str, str] = {
    "application/pdf": "pdf",
    "application/msword": "doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.ms-excel": "xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "text/plain": "txt",
    "image/jpeg": "jpeg",
    "image/png": "png",
}

# Filename extensions accepted for each declared format
EXTENSION_TO_FORMAT: dict[str, str] = {
    ".pdf": "pdf",
    ".doc": "doc",
    ".docx": "docx",
    ".xls": "xls",
    ".xlsx": "xlsx",
    ".txt": "txt",
    ".jpg": "jpeg",
    ".jpeg": "jpeg",
    ".png": "png",
}

# Storage extension derived from the VALIDATED format (never from client input)
STORAGE_EXTENSIONS: dict[str, str] = {
    "pdf": ".pdf",
    "doc": ".doc",
    "docx": ".docx",
    "xls": ".xls",
    "xlsx": ".xlsx",
    "txt": ".txt",
    "jpeg": ".jpg",
    "png": ".png",
}

# Server-side allowlist of accepted MIME types (kept for compatibility)
ALLOWED_CONTENT_TYPES: set[str] = set(MIME_TO_FORMAT)

# Maximum bytes decompressed from a single OOXML entry during validation
# (bounded read guards against ZIP bombs while still proving readability).
_OOXML_PROBE_BYTES = 64 * 1024


def _resolve_storage_root() -> Path:
    """
    Resolve the absolute path to the private document storage directory.
    Creates the directory with restricted permissions if it does not exist.
    """
    storage_root = Path(settings.STORAGE_PATH)
    if not storage_root.is_absolute():
        # Resolve relative paths against the backend directory so storage
        # ends up at backend/storage/ regardless of the working directory.
        storage_root = Path(__file__).resolve().parent.parent.parent.parent / settings.STORAGE_PATH
    storage_root.mkdir(parents=True, exist_ok=True)
    return storage_root


def _safe_extension(filename: str) -> str:
    """Return the lowercased file extension including the leading dot, or empty string."""
    _, ext = os.path.splitext(filename)
    return ext.lower()


def _is_plausible_text(content: bytes) -> bool:
    """
    Text validation rule for the TXT format.

    Plain text has no cryptographic or magic-byte signature, so this rule is
    heuristic by design. A byte sequence is accepted as text only when it:
    - contains no NUL bytes,
    - decodes strictly as UTF-8, and
    - contains no C0 control characters other than tab/newline/return/form-feed,
      and no DEL (0x7F) character.
    """
    if b"\x00" in content:
        return False
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return False
    for ch in text:
        code = ord(ch)
        if code == 0x7F:
            return False
        if code < 32 and ch not in "\t\n\r\f":
            return False
    return True


def _validate_ooxml_zip(content: bytes, main_entry: str) -> bool:
    """
    Validate a DOCX/XLSX (OOXML) archive beyond the bare ZIP signature:
    - must start with the PK\x03\x04 local file header signature,
    - must open as a structurally valid ZIP archive,
    - must contain [Content_Types].xml and the format's main document entry,
    - the main entry must be readable (bounded decompressed probe read).
    Fails closed on malformed, truncated, encrypted or corrupt archives.
    """
    if not content.startswith(b"PK\x03\x04"):
        return False
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            names = set(archive.namelist())
            if "[Content_Types].xml" not in names or main_entry not in names:
                return False
            with archive.open(main_entry) as entry:
                entry.read(_OOXML_PROBE_BYTES)
    except Exception:
        # Fail closed: any malformed/encrypted/corrupt archive is rejected.
        return False
    return True


def _validate_file_format(fmt: str, content: bytes) -> bool:
    """
    Validate actual file bytes against a supported format.
    Returns True only when the content matches the expected signature/structure.
    """
    if fmt == "pdf":
        return content.startswith(b"%PDF")
    if fmt == "jpeg":
        return content.startswith(b"\xff\xd8\xff")
    if fmt == "png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if fmt in ("doc", "xls"):  # legacy OLE2 compound documents (DOC/XLS)
        return content.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
    if fmt == "docx":
        return _validate_ooxml_zip(content, "word/document.xml")
    if fmt == "xlsx":
        return _validate_ooxml_zip(content, "xl/workbook.xml")
    if fmt == "txt":
        return _is_plausible_text(content)
    return False


def _cleanup_stored_file(storage_path: Path, owner_id: str) -> None:
    """
    Best-effort removal of a stored (or partially stored) file during a
    failed upload. Cleanup failures are logged by exception class only and
    are never surfaced to API clients: the original upload failure remains
    the reported error, and no filesystem details leak into responses.
    """
    try:
        storage_path.unlink(missing_ok=True)
    except Exception as exc:
        logger.error(
            "Stored-file cleanup failed for user %s: %s",
            owner_id,
            exc.__class__.__name__,
        )


@router.post(
    "/upload",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a document",
    description=(
        "Upload a file and store it privately on the server. "
        "Requires authentication. Returns document metadata without the storage path."
    ),
)
async def upload_document(
    request: Request,
    file: UploadFile = File(..., description="The document file to upload"),
    description: str | None = Query(default=None, max_length=500, description="Optional document description"),
    category: str | None = Query(default=None, max_length=100, description="Optional document category"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> DocumentResponse:
    """
    Upload and privately store a document.

    Security guarantees:
    - Requires a valid authenticated user (Bearer JWT).
    - Validates file size against MAX_UPLOAD_SIZE_MB.
    - Validates actual file content against known magic-byte signatures
      rather than trusting the client-supplied MIME type or extension.
    - Derives the stored file extension from the validated format.
    - Stores the file under a UUID-based filename to prevent path traversal.
    - Never returns the server-side storage path in the response.
    - Cleans up partial files on write failure and stored files on DB failure.
    - Fails safely without leaking internal paths on database or I/O errors.
    """
    max_bytes = settings.max_upload_size_bytes

    # -----------------------------------------------------------------------
    # 1. Read the file content and enforce size limit
    # -----------------------------------------------------------------------
    try:
        content = await file.read(max_bytes + 1)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to read uploaded file.",
        )

    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum allowed size of {settings.MAX_UPLOAD_SIZE_MB} MB.",
        )

    if len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    # -----------------------------------------------------------------------
    # 2. Validate file content via magic-byte inspection
    # -----------------------------------------------------------------------
    detected_format = validate_file_content(content)

    if detected_format is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                "File content does not match any supported format. "
                "Allowed types: PDF, Word, Excel, plain text, JPEG, PNG."
            ),
        )

    # Use the validated MIME type and extension (ignore client-supplied values)
    content_type = detected_format.mime_type
    extension = detected_format.extension

    original_filename = file.filename or "upload"

    # -----------------------------------------------------------------------
    # 3. Build a UUID-based storage filename to prevent path traversal
    # -----------------------------------------------------------------------
    storage_filename = f"{uuid.uuid4().hex}{extension}"
    object_key = f"{current_user.id}/{storage_filename}"

    # -----------------------------------------------------------------------
    # 4. Persist file to storage (with cleanup on failure)
    # -----------------------------------------------------------------------
    if is_r2_configured(settings):
        try:
            await upload_to_r2(object_key, content, content_type)
        except Exception as exc:
            try:
                await delete_from_r2(object_key)
            except Exception:
                pass
            logger.error(
                "Failed to write document to object storage for user %s: %s",
                current_user.id,
                exc.__class__.__name__,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Document storage failed. Please try again later.",
            ) from None
        stored_path_value = object_key
    else:
        storage_root = _resolve_storage_root()
        # Isolate each owner's documents in their own subdirectory
        owner_dir = storage_root / current_user.id
        owner_dir.mkdir(parents=True, exist_ok=True)
        storage_path = owner_dir / storage_filename
        try:
            storage_path.write_bytes(content)
        except OSError as exc:
            # Clean up any partial file that may have been created
            try:
                storage_path.unlink(missing_ok=True)
            except OSError:
                pass
            logger.error(
                "Failed to write document to storage for user %s: %s",
                current_user.id,
                exc.__class__.__name__,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Document storage failed. Please try again later.",
            ) from None
        stored_path_value = str(storage_path)

    # -----------------------------------------------------------------------
    # 5. Persist metadata record to MongoDB
    # -----------------------------------------------------------------------
    doc = DocumentInDB(
        filename=original_filename,
        content_type=content_type,
        size_bytes=len(content),
        owner_id=current_user.id,
        storage_path=stored_path_value,
        description=description,
        category=category,
    )

    doc_dict = doc.model_dump()
    doc_dict["_id"] = doc.id

    try:
        await db["documents"].insert_one(doc_dict)
        logger.info(
            "Document %s uploaded by user %s (%d bytes).",
            doc.id,
            current_user.id,
            doc.size_bytes,
        )
    except PyMongoError as exc:
        # Roll back stored file to avoid orphaned storage
        if is_r2_configured(settings):
            try:
                await delete_from_r2(object_key)
            except Exception:
                pass
        else:
            try:
                storage_path.unlink(missing_ok=True)
            except OSError:
                pass
        logger.error(
            "Database error while saving document metadata for user %s: %s",
            current_user.id,
            exc.__class__.__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is temporarily unavailable. Please try again later.",
        ) from None

    await record_audit_event(
        db,
        action=AuditAction.DOCUMENT_UPLOAD,
        outcome=AuditOutcome.SUCCESS,
        actor_id=current_user.id,
        document_id=doc.id,
        status_code=201,
        request=request,
    )

    return DocumentResponse(
        id=doc.id,
        filename=doc.filename,
        content_type=doc.content_type,
        size_bytes=doc.size_bytes,
        owner_id=doc.owner_id,
        status=doc.status,
        description=doc.description,
        category=doc.category,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


@router.get(
    "/",
    response_model=DocumentListResponse,
    status_code=status.HTTP_200_OK,
    summary="List accessible documents",
    description=(
        "Return a paginated list of documents owned by or shared with the authenticated user. "
        "Includes documents where the user holds an active read or edit permission grant. "
        "Only active documents are returned. Storage paths are never exposed."
    ),
)
async def list_documents(
    skip: int = Query(default=0, ge=0, description="Number of documents to skip (for pagination)"),
    limit: int = Query(default=20, ge=1, le=100, description="Maximum number of documents to return"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> DocumentListResponse:
    """
    List documents owned by or shared with the currently authenticated user.

    Returns the union of:
    1. Documents where owner_id == current_user.id (own documents).
    2. Documents where an active permission grant exists with grantee_id == current_user.id
       and permission_level is 'read' or 'edit'.

    Security guarantees:
    - Excludes soft-deleted documents (status != 'deleted').
    - Duplicate documents (e.g. if somehow both conditions match) are deduplicated by ID.
    - Pagination (skip/limit) applies to the merged, sorted result set.
    - Never returns storage paths.
    - Fails safely on database outages with 503.
    """
    try:
        # 1. Fetch all active permissions granted to this user
        perm_cursor = db["permissions"].find({"grantee_id": current_user.id})
        perms_raw = await perm_cursor.to_list(length=10000)
    except PyMongoError as exc:
        logger.error(
            "Database error while fetching shared permissions for user %s: %s",
            current_user.id,
            exc.__class__.__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is temporarily unavailable. Please try again later.",
        ) from None

    # Collect document IDs that have been shared with this user (read or edit level)
    shared_doc_ids: list[str] = [
        p["document_id"]
        for p in perms_raw
        if p.get("permission_level") in ("read", "edit")
    ]

    # 2. Fetch own documents
    own_query = {
        "owner_id": current_user.id,
        "status": {"$ne": "deleted"},
    }
    try:
        own_cursor = db["documents"].find(own_query).sort("created_at", -1)
        own_docs_raw = await own_cursor.to_list(length=100000)
    except PyMongoError as exc:
        logger.error(
            "Database error while listing own documents for user %s: %s",
            current_user.id,
            exc.__class__.__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is temporarily unavailable. Please try again later.",
        ) from None

    # 3. Fetch shared documents that are not owned by current user and not deleted
    seen_ids: set[str] = {str(d.get("id") or d.get("_id")) for d in own_docs_raw}
    shared_docs_raw: list[dict] = []
    if shared_doc_ids:
        try:
            # Fetch each shared document individually to avoid $in query issues
            # with the dual id/_id field convention used throughout the codebase.
            for doc_id in shared_doc_ids:
                if doc_id in seen_ids:
                    # Already in own_docs (owner cannot be grantee, but guard anyway)
                    continue
                shared_doc = await db["documents"].find_one({
                    "$or": [{"id": doc_id}, {"_id": doc_id}],
                    "status": {"$ne": "deleted"},
                })
                if shared_doc is not None:
                    resolved_id = str(shared_doc.get("id") or shared_doc.get("_id"))
                    if resolved_id not in seen_ids:
                        seen_ids.add(resolved_id)
                        shared_docs_raw.append(shared_doc)
        except PyMongoError as exc:
            logger.error(
                "Database error while fetching shared documents for user %s: %s",
                current_user.id,
                exc.__class__.__name__,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database service is temporarily unavailable. Please try again later.",
            ) from None

    # 4. Merge, sort by created_at descending, paginate
    all_docs_raw = own_docs_raw + shared_docs_raw
    all_docs_raw.sort(key=lambda d: d.get("created_at") or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

    total = len(all_docs_raw)
    paginated = all_docs_raw[skip: skip + limit]

    documents = [
        DocumentResponse(
            id=str(doc.get("id") or doc.get("_id")),
            filename=doc["filename"],
            content_type=doc["content_type"],
            size_bytes=doc["size_bytes"],
            owner_id=doc["owner_id"],
            status=doc["status"],
            description=doc.get("description"),
            category=doc.get("category"),
            created_at=doc["created_at"],
            updated_at=doc.get("updated_at"),
        )
        for doc in paginated
    ]

    return DocumentListResponse(documents=documents, total=total)


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    status_code=status.HTTP_200_OK,
    summary="Get document metadata",
    description=(
        "Return metadata for a specific document. "
        "Requires authenticated access with owner permission or an active read/edit grant. "
        "Storage path is never exposed."
    ),
)
async def get_document(
    document_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> DocumentResponse:
    """
    Get document metadata.
    Enforces central read authorization (owner or active grantee).
    """
    doc = await verify_document_read_access(document_id, current_user, db)
    return DocumentResponse(
        id=str(doc.get("id") or doc.get("_id")),
        filename=doc["filename"],
        content_type=doc["content_type"],
        size_bytes=doc["size_bytes"],
        owner_id=doc["owner_id"],
        status=doc["status"],
        description=doc.get("description"),
        category=doc.get("category"),
        created_at=doc["created_at"],
        updated_at=doc.get("updated_at"),
    )


@router.get(
    "/{document_id}/download",
    status_code=status.HTTP_200_OK,
    summary="Download a document",
    description=(
        "Download the document file. "
        "Accessible to document owners and users with active read or edit permission grants. "
        "Permissions are evaluated on live database state on every request. "
        "Storage path is resolved from server-side metadata and never exposed."
    ),
)
async def download_document(
    document_id: str,
    request: Request,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> FileResponse:
    """
    Download a document by ID.

    Security guarantees:
    - Enforces central read authorization (owner or active read/edit grantee).
    - Checks live MongoDB state on every request; revoking permission immediately prevents downloads.
    - Resolves storage path strictly from server-side database metadata; never accepts paths from client.
    - Never exposes internal storage paths in responses, headers, or error messages.
    - Returns safe 404 responses for deleted documents and missing storage files.
    - Records audit events for both successful and denied download attempts.
    """
    try:
        doc = await verify_document_read_access(document_id, current_user, db)
    except HTTPException as exc:
        # Record denied access event before re-raising
        await record_audit_event(
            db,
            action=AuditAction.DOCUMENT_DOWNLOAD,
            outcome=AuditOutcome.DENIED,
            actor_id=current_user.id,
            document_id=document_id,
            status_code=exc.status_code,
            reason="access_denied",
            request=request,
        )
        raise

    storage_path_str = doc.get("storage_path")
    if not storage_path_str:
        logger.error("Document metadata for %s is missing storage_path", document_id)
        await record_audit_event(
            db,
            action=AuditAction.DOCUMENT_DOWNLOAD,
            outcome=AuditOutcome.DENIED,
            actor_id=current_user.id,
            document_id=document_id,
            status_code=404,
            reason="storage_path_missing",
            request=request,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document file not found.",
        )

    file_path = Path(storage_path_str)
    filename = doc.get("filename") or "document"
    content_type = doc.get("content_type") or "application/octet-stream"

    if file_path.is_file():
        # Stored on local filesystem (dev / tests / cached files)
        await record_audit_event(
            db,
            action=AuditAction.DOCUMENT_DOWNLOAD,
            outcome=AuditOutcome.SUCCESS,
            actor_id=current_user.id,
            document_id=document_id,
            status_code=200,
            request=request,
        )

        return FileResponse(
            path=str(file_path),
            filename=filename,
            media_type=content_type,
        )

    # File not found on local filesystem; retrieve from Cloudflare R2 / S3
    try:
        file_bytes = await download_from_r2(storage_path_str)
    except FileNotFoundError:
        logger.error("Stored file for document %s is missing from storage", document_id)
        await record_audit_event(
            db,
            action=AuditAction.DOCUMENT_DOWNLOAD,
            outcome=AuditOutcome.DENIED,
            actor_id=current_user.id,
            document_id=document_id,
            status_code=404,
            reason="file_not_found",
            request=request,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document file not found.",
        )
    except Exception as exc:
        logger.error("Failed to retrieve document %s from storage: %s", document_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve document from storage.",
        )

    await record_audit_event(
        db,
        action=AuditAction.DOCUMENT_DOWNLOAD,
        outcome=AuditOutcome.SUCCESS,
        actor_id=current_user.id,
        document_id=document_id,
        status_code=200,
        request=request,
    )

    return Response(
        content=file_bytes,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.patch(
    "/{document_id}",
    response_model=DocumentResponse,
    status_code=status.HTTP_200_OK,
    summary="Update document metadata",
    description=(
        "Update supported document metadata such as filename, description, or category. "
        "Only the owner or a user with edit permission may update metadata. "
        "Read-only users and unauthorized users are denied."
    ),
)
@router.put(
    "/{document_id}",
    response_model=DocumentResponse,
    status_code=status.HTTP_200_OK,
    summary="Update document metadata",
    description=(
        "Update supported document metadata such as filename, description, or category. "
        "Only the owner or a user with edit permission may update metadata. "
        "Read-only users and unauthorized users are denied."
    ),
)
async def update_document_metadata(
    document_id: str,
    update_in: DocumentUpdateRequest,
    request: Request,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> DocumentResponse:
    """
    Update supported document metadata.

    Security guarantees:
    - Enforces central edit authorization (owner or active edit grantee).
    - Read-only users and ungranted users are denied with 403 Forbidden.
    - Validates all input via DocumentUpdateRequest schema.
    - Strictly forbids modification of owner_id, storage_path, id, status, size_bytes, or content_type.
    - Never exposes internal storage paths in responses.
    - Fails safely on database outages with 503.
    - Records audit events for both successful and denied update attempts.
    """
    try:
        doc = await verify_document_edit_access(document_id, current_user, db)
    except HTTPException as exc:
        await record_audit_event(
            db,
            action=AuditAction.DOCUMENT_UPDATE,
            outcome=AuditOutcome.DENIED,
            actor_id=current_user.id,
            document_id=document_id,
            status_code=exc.status_code,
            reason="access_denied",
            request=request,
        )
        raise
    actual_doc_id = str(doc.get("id") or doc.get("_id"))

    # Extract supported metadata fields
    update_fields: dict[str, Any] = {}
    if update_in.filename is not None:
        update_fields["filename"] = update_in.filename
    if update_in.description is not None:
        update_fields["description"] = update_in.description
    if update_in.category is not None:
        update_fields["category"] = update_in.category

    now = datetime.now(timezone.utc)
    update_fields["updated_at"] = now

    try:
        await db["documents"].update_one(
            {"$or": [{"id": actual_doc_id}, {"_id": actual_doc_id}]},
            {"$set": update_fields},
        )
    except PyMongoError as exc:
        logger.error(
            "Database error while updating document %s: %s",
            actual_doc_id,
            exc.__class__.__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is temporarily unavailable. Please try again later.",
        ) from None

    try:
        updated_doc = await db["documents"].find_one({
            "$or": [{"id": actual_doc_id}, {"_id": actual_doc_id}],
            "status": {"$ne": "deleted"},
        })
    except PyMongoError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is temporarily unavailable. Please try again later.",
        ) from None

    if updated_doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    logger.info(
        "User %s updated metadata for document %s: %s",
        current_user.id,
        actual_doc_id,
        list(update_fields.keys()),
    )

    await record_audit_event(
        db,
        action=AuditAction.DOCUMENT_UPDATE,
        outcome=AuditOutcome.SUCCESS,
        actor_id=current_user.id,
        document_id=actual_doc_id,
        status_code=200,
        request=request,
    )

    return DocumentResponse(
        id=actual_doc_id,
        filename=updated_doc["filename"],
        content_type=updated_doc["content_type"],
        size_bytes=updated_doc["size_bytes"],
        owner_id=updated_doc["owner_id"],
        status=updated_doc["status"],
        description=updated_doc.get("description"),
        category=updated_doc.get("category"),
        created_at=updated_doc["created_at"],
        updated_at=updated_doc.get("updated_at"),
    )


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a document",
    description=(
        "Soft-delete a document and safely clean up its storage file. "
        "Strictly restricted to the document owner. "
        "Ensures deleted documents cannot be listed, downloaded, or accessed."
    ),
)
async def delete_document(
    document_id: str,
    request: Request,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> Response:
    """
    Delete a document.

    Security guarantees:
    - Strictly restricted to the document owner via verify_document_owner.
    - Non-owners (including read and edit grantees) are denied with 403 Forbidden.
    - Performs soft deletion in MongoDB by setting status='deleted'.
    - Cleans up associated permission grants in permissions collection.
    - Storage cleanup is handled safely: only removes files belonging to the owner,
      never permanently deletes another user's file or files outside the storage root.
    - Storage cleanup failures are handled safely and consistently without leaking internal paths.
    - Deleted documents cannot be listed, downloaded, or accessed by ID.
    - Records audit events for successful and denied deletion attempts.
    """
    try:
        doc = await verify_document_owner(document_id, current_user, db)
    except HTTPException as exc:
        await record_audit_event(
            db,
            action=AuditAction.DOCUMENT_DELETE,
            outcome=AuditOutcome.DENIED,
            actor_id=current_user.id,
            document_id=document_id,
            status_code=exc.status_code,
            reason="access_denied",
            request=request,
        )
        raise
    actual_doc_id = str(doc.get("id") or doc.get("_id"))

    # Strictly enforce that caller is the owner
    if doc.get("owner_id") != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: Only the document owner can delete this document.",
        )

    # 1. Soft-delete the document record in MongoDB
    now = datetime.now(timezone.utc)
    try:
        await db["documents"].update_one(
            {"$or": [{"id": actual_doc_id}, {"_id": actual_doc_id}]},
            {"$set": {"status": DocumentStatus.DELETED.value, "updated_at": now}},
        )
        # Clean up any active permission grants for this document
        await db["permissions"].delete_many({"document_id": actual_doc_id})
    except PyMongoError as exc:
        logger.error(
            "Database error while soft-deleting document %s: %s",
            actual_doc_id,
            current_user.id,
            exc.__class__.__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is temporarily unavailable. Please try again later.",
        ) from None

    # 2. Safe storage cleanup
    storage_path_str = doc.get("storage_path")
    if storage_path_str:
        if is_r2_configured(settings):
            try:
                await delete_from_r2(storage_path_str)
            except Exception as exc:
                logger.error(
                    "Stored object cleanup failed for document %s user %s: %s",
                    actual_doc_id,
                    current_user.id,
                    exc.__class__.__name__,
                )
        try:
            file_path = Path(storage_path_str).resolve()
            storage_root = _resolve_storage_root().resolve()
            owner_dir = (storage_root / current_user.id).resolve()

            # Security verification: Ensure file belongs to the current user's document storage
            # and is within storage root. Never delete files outside owner directory or another user's directory.
            is_owner_file = False
            if file_path.is_relative_to(owner_dir):
                is_owner_file = True
            elif file_path.is_relative_to(storage_root) and file_path.parent == storage_root:
                is_owner_file = True

            if is_owner_file and file_path.is_file():
                file_path.unlink(missing_ok=True)
            elif not is_owner_file:
                logger.warning(
                    "Storage cleanup security check: file %s is not within owner storage for doc %s",
                    file_path.name,
                    actual_doc_id,
                )
        except Exception as exc:
            # Handle storage cleanup failure safely and consistently without leaking internal details
            logger.error(
                "Stored file cleanup failed for document %s user %s: %s",
                actual_doc_id,
                current_user.id,
                exc.__class__.__name__,
            )

    logger.info(
        "Document %s soft-deleted by owner %s.",
        actual_doc_id,
        current_user.id,
    )

    await record_audit_event(
        db,
        action=AuditAction.DOCUMENT_DELETE,
        outcome=AuditOutcome.SUCCESS,
        actor_id=current_user.id,
        document_id=actual_doc_id,
        status_code=204,
        request=request,
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{document_id}/permissions",
    response_model=PermissionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Grant document permission",
    description=(
        "Grant read or edit access to a registered user for this document. "
        "Only the document owner can grant permissions. "
        "Recipient must be an active registered user."
    ),
)
async def grant_permission(
    document_id: str,
    grant_in: PermissionGrantRequest,
    request: Request,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> PermissionResponse:
    """
    Grant document permission to a registered user.

    Security guarantees:
    - Verifies document exists and is not deleted.
    - Strictly requires document ownership (never trusts owner_id from request).
    - Verifies grantee user exists in database and is active.
    - Prevents owner from granting access to themselves.
    - Prevents duplicate permission grants for same document and user.
    - Validates permission level ('read' or 'edit').
    - Records audit events for grant success and denied attempts.
    """
    # 1. Verify caller is the document owner
    try:
        doc = await verify_document_owner(document_id, current_user, db)
    except HTTPException as exc:
        await record_audit_event(
            db,
            action=AuditAction.PERMISSION_GRANT,
            outcome=AuditOutcome.DENIED,
            actor_id=current_user.id,
            document_id=document_id,
            status_code=exc.status_code,
            reason="access_denied",
            request=request,
        )
        raise
    actual_doc_id = str(doc.get("id") or doc.get("_id"))

    # 2. Resolve recipient user
    if not grant_in.grantee_id and not grant_in.grantee_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either grantee_id or grantee_email must be provided.",
        )

    try:
        if grant_in.grantee_id:
            recipient = await db["users"].find_one({
                "$or": [{"id": grant_in.grantee_id.strip()}, {"_id": grant_in.grantee_id.strip()}],
            })
        else:
            normalized_email = grant_in.grantee_email.strip().lower()
            recipient = await db["users"].find_one({"email": normalized_email})
    except PyMongoError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is temporarily unavailable. Please try again later.",
        ) from None

    if recipient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recipient user does not exist or has been removed.",
        )

    if not recipient.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot grant permissions to a deactivated user account.",
        )

    recipient_id = str(recipient.get("id") or recipient.get("_id"))
    recipient_email = recipient.get("email")

    # 3. Disallow self-grant
    if recipient_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot grant permission to the document owner.",
        )

    # 4. Check for duplicate permission grant
    try:
        existing_perm = await db["permissions"].find_one({
            "document_id": actual_doc_id,
            "grantee_id": recipient_id,
        })
    except PyMongoError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is temporarily unavailable. Please try again later.",
        ) from None

    if existing_perm is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Permission grant already exists for this user and document.",
        )

    # 5. Build and persist permission record
    perm = PermissionInDB(
        document_id=actual_doc_id,
        owner_id=current_user.id,
        grantee_id=recipient_id,
        grantee_email=recipient_email,
        permission_level=grant_in.permission_level,
    )
    perm_dict = perm.model_dump()
    perm_dict["_id"] = perm.id

    try:
        await db["permissions"].insert_one(perm_dict)
        logger.info(
            "User %s granted %s permission on document %s to user %s.",
            current_user.id,
            perm.permission_level.value,
            actual_doc_id,
            recipient_id,
        )
    except DuplicateKeyError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Permission grant already exists for this user and document.",
        ) from None
    except PyMongoError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is temporarily unavailable. Please try again later.",
        ) from None

    await record_audit_event(
        db,
        action=AuditAction.PERMISSION_GRANT,
        outcome=AuditOutcome.SUCCESS,
        actor_id=current_user.id,
        document_id=actual_doc_id,
        status_code=201,
        reason=f"granted_{perm.permission_level.value}_to_{recipient_id}",
        request=request,
    )

    return PermissionResponse(
        id=perm.id,
        document_id=perm.document_id,
        owner_id=perm.owner_id,
        grantee_id=perm.grantee_id,
        grantee_email=perm.grantee_email,
        permission_level=perm.permission_level,
        created_at=perm.created_at,
        updated_at=perm.updated_at,
    )


@router.get(
    "/{document_id}/permissions",
    response_model=PermissionListResponse,
    status_code=status.HTTP_200_OK,
    summary="List document permissions",
    description=(
        "List all active permission grants for a document. "
        "Only the document owner can list permissions. "
        "Strictly excludes credentials, hashes, and internal paths."
    ),
)
async def list_permissions(
    document_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> PermissionListResponse:
    """
    List active permissions for a document.
    Only the document owner may access this listing.
    """
    doc = await verify_document_owner(document_id, current_user, db)
    actual_doc_id = str(doc.get("id") or doc.get("_id"))

    try:
        cursor = db["permissions"].find({"document_id": actual_doc_id})
        perms_raw = await cursor.to_list(length=500)
    except PyMongoError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is temporarily unavailable. Please try again later.",
        ) from None

    permissions = [
        PermissionResponse(
            id=str(p.get("id") or p.get("_id")),
            document_id=p["document_id"],
            owner_id=p["owner_id"],
            grantee_id=p["grantee_id"],
            grantee_email=p.get("grantee_email"),
            permission_level=PermissionLevel(p["permission_level"]),
            created_at=p["created_at"],
            updated_at=p["updated_at"],
        )
        for p in perms_raw
    ]

    return PermissionListResponse(permissions=permissions, total=len(permissions))


@router.delete(
    "/{document_id}/permissions/{grantee_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke document permission",
    description=(
        "Immediately revoke document permission for a user. "
        "Only the document owner can revoke permissions. "
        "Subsequent access checks immediately deny access."
    ),
)
async def revoke_permission(
    document_id: str,
    grantee_id: str,
    request: Request,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> Response:
    """
    Revoke a document permission grant.
    Enforces live database check so revocation takes immediate effect.
    Records audit events for both successful and denied revocation attempts.
    """
    try:
        doc = await verify_document_owner(document_id, current_user, db)
    except HTTPException as exc:
        await record_audit_event(
            db,
            action=AuditAction.PERMISSION_REVOKE,
            outcome=AuditOutcome.DENIED,
            actor_id=current_user.id,
            document_id=document_id,
            status_code=exc.status_code,
            reason="access_denied",
            request=request,
        )
        raise
    actual_doc_id = str(doc.get("id") or doc.get("_id"))

    try:
        result = await db["permissions"].delete_one({
            "document_id": actual_doc_id,
            "grantee_id": grantee_id.strip(),
        })
    except PyMongoError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is temporarily unavailable. Please try again later.",
        ) from None

    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Permission grant not found for this user and document.",
        )

    logger.info(
        "User %s revoked permission on document %s for user %s.",
        current_user.id,
        actual_doc_id,
        grantee_id,
    )

    await record_audit_event(
        db,
        action=AuditAction.PERMISSION_REVOKE,
        outcome=AuditOutcome.SUCCESS,
        actor_id=current_user.id,
        document_id=actual_doc_id,
        status_code=204,
        reason=f"revoked_from_{grantee_id.strip()[:50]}",
        request=request,
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)

