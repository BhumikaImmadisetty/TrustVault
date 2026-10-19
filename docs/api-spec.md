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
| `POST` | `/auth/register` | Register a new user account with hashed password | Public | `[PLANNED]` |
| `POST` | `/auth/login` | Authenticate with credentials and obtain JWT Bearer token | Public | `[PLANNED]` |
| `GET` | `/auth/me` | Fetch authenticated user profile & system role | Authenticated (Any) | `[PLANNED]` |

### Example Request: `POST /api/v1/auth/login`
```json
{
  "email": "user@example.com",
  "password": "SecurePassword123!"
}
```

### Example Response: `200 OK`
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user": {
    "id": "664fa7...",
    "email": "user@example.com",
    "full_name": "Jane Doe",
    "system_role": "user"
  }
}
```

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
