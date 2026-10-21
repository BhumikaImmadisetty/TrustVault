# TrustVault - API Specification

> **Document Status**: **Partially Implemented**
> Authentication endpoints and document upload/listing are implemented and tested.
> Sharing, download streaming, deletion, permission management, and audit endpoints are planned.

---

## Base URL
`/api/v1`

---

## 1. Authentication Endpoints

| Method | Endpoint | Purpose | Required Role / Permission | Status |
| :--- | :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/auth/register` (alias `/auth/register`) | Register a new user account with hashed password | Public | `[IMPLEMENTED]` |
| `POST` | `/api/v1/auth/login` (alias `/auth/login`) | Authenticate with credentials and obtain JWT Bearer token | Public | `[IMPLEMENTED]` |
| `GET` | `/api/v1/auth/me` (alias `/auth/me`) | Fetch authenticated user profile & system role | Authenticated (Bearer Token) | `[IMPLEMENTED]` |

### 1.1 User Registration: `POST /api/v1/auth/register`
* **Authentication**: None (Public)
* **Access Control**: Public registration automatically assigns the least-privileged `viewer` role. Supplying `role: "admin"` returns `422 Unprocessable Entity`.
* **Password Policy**: Minimum 8 characters, maximum 128 characters, requiring at least one uppercase letter, one lowercase letter, and one digit. Stored as an Argon2id hash.
* **Email Normalization**: Automatically converted to lowercase with whitespace stripped.

#### Example Request Body
```json
{
  "email": "user@example.com",
  "full_name": "Jane Doe",
  "password": "SecurePassword123!"
}
```

#### Example Response: `201 Created`
```json
{
  "id": "e5b8d234-92cb-46a2-94b1-e405bfef35c1",
  "email": "user@example.com",
  "full_name": "Jane Doe",
  "role": "viewer",
  "is_active": true,
  "created_at": "2026-10-19T12:00:00Z"
}
```

#### Error Responses
* `409 Conflict`: `{"detail": "An account with this email address already exists."}`
* `422 Unprocessable Entity`: Password complexity failure, invalid email syntax, or attempted `role: "admin"` assignment.
* `503 Service Unavailable`: Database service temporarily unreachable.

---

### 1.2 User Login: `POST /api/v1/auth/login`
* **Authentication**: None (Public)
* **Behavior**: Compares submitted candidate password against the stored Argon2id hash. Returns a signed JWT access token (`HS256`, 15-minute expiration default).
* **Security Protection**: Returns an identical generic error message for unknown emails and wrong passwords to eliminate user enumeration vectors.

#### Example Request Body
```json
{
  "email": "user@example.com",
  "password": "SecurePassword123!"
}
```

#### Example Response: `200 OK`
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user": {
    "id": "e5b8d234-92cb-46a2-94b1-e405bfef35c1",
    "email": "user@example.com",
    "full_name": "Jane Doe",
    "role": "viewer",
    "is_active": true,
    "created_at": "2026-10-19T12:00:00Z"
  }
}
```

#### Error Responses
* `401 Unauthorized`: `{"detail": "Invalid email or password"}` (generic for wrong password, missing account, or invalid credentials).
* `401 Unauthorized`: `{"detail": "Account is deactivated. Please contact an administrator."}`
* `503 Service Unavailable`: Database service temporarily unreachable.

---

### 1.3 Current User Profile: `GET /api/v1/auth/me`
* **Authentication**: Required (`Authorization: Bearer <access_token>`)
* **Live Role Verification**: The active user role and account status are dynamically resolved from the MongoDB database on every request. Token claims (such as a forged role claim) are never trusted as authorization grants.

#### Request Headers
```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

#### Example Response: `200 OK`
```json
{
  "id": "e5b8d234-92cb-46a2-94b1-e405bfef35c1",
  "email": "user@example.com",
  "full_name": "Jane Doe",
  "role": "viewer",
  "is_active": true,
  "created_at": "2026-10-19T12:00:00Z"
}
```

#### Error Responses
* `401 Unauthorized`: `{"detail": "Authentication credentials were not provided"}` (Missing Authorization header).
* `401 Unauthorized`: `{"detail": "Invalid authentication scheme; Bearer token required"}` (Non-Bearer scheme).
* `401 Unauthorized`: `{"detail": "Authentication token has expired"}`.
* `401 Unauthorized`: `{"detail": "Could not validate credentials"}` (Tampered token or signature mismatch).
* `401 Unauthorized`: `{"detail": "User account does not exist or has been removed"}`.
* `401 Unauthorized`: `{"detail": "Account is deactivated"}`.
* `503 Service Unavailable`: Database service temporarily unreachable.

---

## 2. Document Management Endpoints

| Method | Endpoint | Purpose | Required Role / Permission | Status |
| :--- | :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/documents/upload` | Upload a document into private server-side storage | Authenticated User (becomes Owner) | `[IMPLEMENTED]` |
| `GET` | `/api/v1/documents/` | List documents owned by the authenticated user | Authenticated User | `[IMPLEMENTED]` |
| `GET` | `/api/v1/documents/{id}` | Get metadata for a specific document | Document Owner or Active Viewer | `[PLANNED]` |
| `GET` | `/api/v1/documents/{id}/download` | Stream binary document content securely | Document Owner or Active Viewer | `[PLANNED]` |
| `DELETE` | `/api/v1/documents/{id}` | Soft-delete document file and metadata | Document Owner | `[PLANNED]` |

---

### 2.1 Upload Document: `POST /api/v1/documents/upload`
* **Authentication**: Required (`Authorization: Bearer <access_token>`)
* **Request**: `multipart/form-data` with a `file` field and an optional `description` query parameter (max 500 characters).
* **Ownership**: The uploaded document is automatically attributed to the authenticated user. The uploader is assigned as the sole owner.
* **File Size Limit**: Configurable via `MAX_UPLOAD_SIZE_MB` (default: 10 MB). Files larger than the configured limit are rejected with `413`.
* **Allowed MIME Types** (validated against a server-side allowlist):
  * `application/pdf`
  * `application/msword`
  * `application/vnd.openxmlformats-officedocument.wordprocessingml.document`
  * `application/vnd.ms-excel`
  * `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
  * `text/plain`
  * `image/jpeg`
  * `image/png`
* **Storage Security**:
  * Files are stored under a server-controlled UUID-based filename. The original filename is retained in metadata only and is never used as the storage path.
  * Each owner's files are isolated in a per-owner subdirectory under the configured `STORAGE_PATH`.
  * The server-side `storage_path` is **never** returned in any API response.
  * If MongoDB insertion fails after a file is written, the stored file is deleted to prevent orphaned storage.

#### Example Request (multipart/form-data)
```
POST /api/v1/documents/upload?description=Q3+Report HTTP/1.1
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
Content-Type: multipart/form-data; boundary=----FormBoundary

------FormBoundary
Content-Disposition: form-data; name="file"; filename="report.pdf"
Content-Type: application/pdf

<binary file content>
------FormBoundary--
```

#### Example Response: `201 Created`
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "filename": "report.pdf",
  "content_type": "application/pdf",
  "size_bytes": 204800,
  "owner_id": "e5b8d234-92cb-46a2-94b1-e405bfef35c1",
  "status": "active",
  "description": "Q3 Report",
  "created_at": "2026-10-19T12:00:00Z"
}
```

> **Note**: `storage_path` is never present in the response. Its absence is verified by automated tests.

#### Error Responses
* `400 Bad Request`: `{"detail": "Uploaded file is empty."}` — Zero-byte uploads rejected.
* `400 Bad Request`: `{"detail": "Failed to read uploaded file."}` — File read error.
* `401 Unauthorized`: Missing, expired, or invalid Bearer token.
* `413 Request Entity Too Large`: File exceeds `MAX_UPLOAD_SIZE_MB`.
* `415 Unsupported Media Type`: MIME type not in the server-side allowlist.
* `500 Internal Server Error`: `{"detail": "Document storage failed. Please try again later."}` — Filesystem write failure.
* `503 Service Unavailable`: MongoDB write failure (stored file is rolled back automatically).

---

### 2.2 List Own Documents: `GET /api/v1/documents/`
* **Authentication**: Required (`Authorization: Bearer <access_token>`)
* **Scope**: Returns only documents where `owner_id` matches the authenticated user's ID. Cross-user document visibility is never granted by this endpoint.
* **Filtering**: Soft-deleted documents (`status: "deleted"`) are excluded from all results by default.
* **Pagination**: Supports `skip` (default: 0, min: 0) and `limit` (default: 20, min: 1, max: 100) query parameters.
* **Sorting**: Results are returned sorted by `created_at` descending (newest first).

#### Example Request
```http
GET /api/v1/documents/?skip=0&limit=20 HTTP/1.1
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

#### Example Response: `200 OK`
```json
{
  "documents": [
    {
      "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "filename": "report.pdf",
      "content_type": "application/pdf",
      "size_bytes": 204800,
      "owner_id": "e5b8d234-92cb-46a2-94b1-e405bfef35c1",
      "status": "active",
      "description": "Q3 Report",
      "created_at": "2026-10-19T12:00:00Z"
    }
  ],
  "total": 1
}
```

> **Note**: `storage_path` is never present in any document object in the listing response.

#### Error Responses
* `401 Unauthorized`: Missing, expired, or invalid Bearer token.
* `503 Service Unavailable`: Database service temporarily unreachable.

---

### 2.3 Get Document Metadata: `GET /api/v1/documents/{id}` `[PLANNED]`
_Not yet implemented._

### 2.4 Download Document: `GET /api/v1/documents/{id}/download` `[PLANNED]`
_Not yet implemented. Will evaluate active permissions before streaming any bytes._

### 2.5 Delete Document: `DELETE /api/v1/documents/{id}` `[PLANNED]`
_Not yet implemented._

---

## 3. Permission Management Endpoints

| Method | Endpoint | Purpose | Required Role / Permission | Status |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/documents/{id}/permissions` | List all active grants for a document | Document Owner | `[PLANNED]` |
| `POST` | `/documents/{id}/permissions` | Grant viewer permission to a specified user email | Document Owner | `[PLANNED]` |
| `DELETE` | `/documents/{id}/permissions/{user_id}` | Immediately revoke viewer permission for a user | Document Owner | `[PLANNED]` |

### Example Request: `POST /api/v1/documents/{id}/permissions`
```json
{
  "grantee_email": "colleague@example.com",
  "permission_level": "viewer"
}
```

### Response on Immediate Revocation: `DELETE /api/v1/documents/{id}/permissions/{user_id}`
* Returns `204 No Content`.
* Subsequent requests by `{user_id}` to `/documents/{id}/download` immediately respond with `403 Forbidden`.

---

## 4. Audit Log Endpoints

| Method | Endpoint | Purpose | Required Role / Permission | Status |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/audit/` | Retrieve paginated audit trail events with filtering by action, outcome, actor, document, and date | Admin Role Only (`role: "admin"`) | `[IMPLEMENTED]` |

### 4.1 List Audit Events: `GET /api/v1/audit/`
* **Authentication**: Required (`Authorization: Bearer <access_token>`)
* **Access Control**: Strictly restricted to users with `role: "admin"` via live database role inspection (`require_admin_user`). Regular users (`owner`, `viewer`) receive `403 Forbidden`. Unauthenticated requests receive `401 Unauthorized`.
* **Query Parameters**:
  * `skip` (int, default `0`, ge `0`): Number of audit records to skip.
  * `limit` (int, default `50`, ge `1`, le `200`): Maximum number of records to return.
  * `action` (string, optional): Filter by action name (e.g. `auth.login`, `document.upload`, `document.download`, `document.update`, `document.delete`, `permission.grant`, `permission.revoke`).
  * `outcome` (string, optional): Filter by outcome (`success` or `denied`).
  * `actor_id` (string, optional): Filter by actor user ID.
  * `document_id` (string, optional): Filter by target document ID.
  * `start_date` (datetime, optional): Filter events on or after UTC datetime (ISO 8601).
  * `end_date` (datetime, optional): Filter events on or before UTC datetime (ISO 8601).
* **Privacy & Security Guarantees**:
  * Strictly excludes passwords, password hashes, JWT tokens, Authorization headers, document contents, and server filesystem paths.
  * Reasons and identifiers are actively sanitized and redacted.
  * Indexed on `timestamp`, `(action, timestamp)`, `(actor_id, timestamp)`, `(document_id, timestamp)`, and `(outcome, timestamp)`.

#### Example Response: `200 OK`
```json
{
  "events": [
    {
      "id": "c1f7f02d-9eb0-4dbb-8260-ae61244e830c",
      "timestamp": "2026-10-20T11:45:00Z",
      "actor_id": "user-abc-123",
      "action": "document.download",
      "document_id": "doc-xyz-789",
      "outcome": "denied",
      "status_code": 403,
      "reason": "access_denied",
      "correlation_id": "corr-req-001"
    }
  ],
  "total": 1,
  "skip": 0,
  "limit": 50
}
```

---

## 5. Administrative Endpoints

| Method | Endpoint | Purpose | Required Role / Permission | Status |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/admin/users` | List all registered users and their status | Admin Role Only | `[PLANNED]` |
| `PATCH` | `/admin/users/{user_id}/status` | Activate or deactivate a user account | Admin Role Only | `[PLANNED]` |

---

## 6. HTTP Status Code Conventions

* `200 OK`: Request succeeded.
* `201 Created`: Resource successfully created (e.g. document uploaded or account registered).
* `204 No Content`: Successful deletion or revocation with no response body.
* `400 Bad Request`: Validation failure, malformed payload, or empty file upload.
* `401 Unauthorized`: Missing, expired, or invalid authentication credentials.
* `403 Forbidden`: Authenticated user lacks permission to access the resource.
* `404 Not Found`: Resource does not exist or user lacks visibility.
* `409 Conflict`: Duplicate resource (e.g. email address already registered).
* `413 Request Entity Too Large`: Uploaded file exceeds the configured `MAX_UPLOAD_SIZE_MB` limit.
* `415 Unsupported Media Type`: Uploaded file MIME type is not in the server-side allowlist.
* `422 Unprocessable Entity`: Request body fails schema validation (e.g. password complexity, invalid email, forbidden role).
* `500 Internal Server Error`: Filesystem write failure during document storage.
* `503 Service Unavailable`: Database service temporarily unreachable.
