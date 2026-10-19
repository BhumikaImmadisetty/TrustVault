# TrustVault - Preliminary API Specification

> **Document Status**: **Preliminary Planned Specification**  
> *Notice: All endpoints listed below are planned for implementation in subsequent phases. None are currently active or implemented.*

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
| `POST` | `/documents/upload` | Upload a new document into private vault storage | Authenticated User (becomes Owner) | `[PLANNED]` |
| `GET` | `/documents` | List documents owned by or explicitly shared with user | Authenticated User | `[PLANNED]` |
| `GET` | `/documents/{id}` | Get metadata for a specific document | Document Owner or Active Viewer | `[PLANNED]` |
| `GET` | `/documents/{id}/download` | Stream binary content of document | Document Owner or Active Viewer | `[PLANNED]` |
| `DELETE` | `/documents/{id}` | Permanently delete document file and metadata | Document Owner | `[PLANNED]` |

### Notes on `/documents/{id}/download`:
* Evaluates active permission in MongoDB before sending byte 1.
* Returns standard security headers (`Cache-Control: no-store, private`, `Content-Disposition: attachment`).
* Generates an audit record for both `200 OK` and `403 Forbidden` outcomes.

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
| `GET` | `/audit/document/{id}` | Retrieve audit trail for a specific document | Document Owner | `[PLANNED]` |
| `GET` | `/audit/global` | Retrieve system-wide audit logs with filters | Admin Role Only | `[PLANNED]` |

### Example Audit Record:
```json
{
  "id": "664fb1...",
  "timestamp": "2026-10-19T10:45:00Z",
  "actor_user_id": "664fa7...",
  "actor_email": "attacker@example.com",
  "action": "DOCUMENT_DOWNLOAD",
  "document_id": "664fc9...",
  "status": "DENIED",
  "reason": "REVOKED_ACCESS",
  "ip_address": "192.168.1.105"
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
* `400 Bad Request`: Validation failure or malformed payload.
* `401 Unauthorized`: Missing, expired, or invalid authentication credentials.
* `403 Forbidden`: Authenticated user lacks permission to access the resource.
* `404 Not Found`: Resource does not exist or user lacks visibility.
* `413 Payload Too Large`: Uploaded file exceeds configured size limit.
