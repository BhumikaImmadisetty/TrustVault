# TrustVault - Threat Model & Security Analysis

> **Document Status**: **Planning & Design Stage**  
> *Notice: This document outlines potential security threats against TrustVault, planned mitigations, and the automated security tests to be implemented. None of the mitigations or tests are claimed to be complete yet.*

---

## 1. Overview & Threat Modeling Methodology

TrustVault is designed to handle confidential document sharing under strict access controls. A threat model ensures vulnerabilities are proactively anticipated, mitigated, and validated through automated testing.

We evaluate threats based on the STRIDE model (Spoofing, Tampering, Repudiation, Information Disclosure, Denial of Service, Elevation of Privilege) with specific focus on web-based file sharing and authorization flaws.

---

## 2. Threat Catalog, Mitigations, and Planned Tests

### Threat 1: Unauthorised Document Access (IDOR / Broken Object-Level Authorization)
* **Description**: An authenticated user (e.g., User B) guesses or intercepts the document ID belonging to User A and attempts to fetch document metadata or content directly.
* **STRIDE Category**: Information Disclosure / Elevation of Privilege.
* **Potential Impact**: High. Unauthorized disclosure of confidential files across user boundaries.
* **Planned Mitigations**:
  * Implement strict server-side authorization checks on every document endpoint (`/documents/{id}`, `/documents/{id}/download`).
  * Never trust client-supplied identity; verify user identity solely from authenticated server-side session/JWT.
  * Check the database on every request to ensure the requester is either the document Owner or an explicitly active Viewer.
* **Planned Verification Tests**:
  * `test_isolation.py::test_user_cannot_access_unshared_document`: User B attempts `GET /api/v1/documents/{doc_id_A}` and expects `403 Forbidden` or `404 Not Found`.
  * `test_isolation.py::test_stranger_cannot_download_document`: Asserts download stream returns `403 Forbidden` for non-permitted users.

---

### Threat 2: Insecure Downloads (Direct Static File Exposure & Reusable Links)
* **Description**: Uploaded files are placed in a publicly accessible web root (e.g., `/static/uploads/file.pdf`), or download links rely on predictable/reusable URLs that do not re-verify permissions at the moment of download.
* **STRIDE Category**: Information Disclosure.
* **Potential Impact**: Critical. Files can be retrieved by anyone with the URL, bypassing authentication entirely.
* **Planned Mitigations**:
  * Store all uploaded files in a dedicated storage directory outside the web server's static directory.
  * Serve files strictly via an authenticated streaming endpoint (`GET /api/v1/documents/{id}/download`).
  * Require a valid Bearer token and evaluate active permissions in the database before sending any file chunk.
  * Add HTTP headers to prevent unsafe caching of sensitive documents: `Cache-Control: no-store, no-cache, must-revalidate, private`.
* **Planned Verification Tests**:
  * `test_permissions.py::test_direct_url_without_auth_header_rejected`: Unauthenticated request to download returns `401 Unauthorized`.
  * `test_permissions.py::test_cache_control_headers_present`: Verifies security headers on file streaming responses.

---

### Threat 3: Stolen Credentials & Plaintext Password Exposure
* **Description**: Passwords leaked from database breaches or exposed in logs/transits; compromised user sessions due to weak or unhashed credentials.
* **STRIDE Category**: Spoofing / Information Disclosure.
* **Potential Impact**: Critical. Full account takeover.
* **Planned Mitigations**:
  * Passwords must **never** be stored as plaintext or using outdated hash algorithms (like MD5 or SHA1).
  * Use salted `bcrypt` with an appropriate work factor for all password hashing.
  * Enforce strong password complexity rules during registration.
  * Transmit passwords and tokens only over HTTPS/TLS in production.
  * Store application secrets and database credentials in `.env` files excluded from version control.
* **Planned Verification Tests**:
  * `test_auth.py::test_password_is_properly_hashed`: Verifies the database stores only a bcrypt hash, never the raw password.
  * `test_auth.py::test_invalid_credentials_rejected`: Verifies timing-resistant rejection of invalid passwords.

---

### Threat 4: Privilege Escalation (Vertical and Horizontal)
* **Description**: A regular user manipulates request payloads or headers to elevate their role to `admin` or `owner` of another user's document, gaining unauthorized management capabilities.
* **STRIDE Category**: Elevation of Privilege.
* **Potential Impact**: Critical. Non-admin users creating or editing accounts, or regular viewers revoking access from true owners.
* **Planned Mitigations**:
  * Reject any client-provided `role` attribute during standard user registration (force default role to standard user).
  * Enforce role validation using server-side dependencies (`require_admin` dependency).
  * Prevent Viewers from invoking permission management endpoints (`POST /documents/{id}/permissions` must strictly require `owner` status).
* **Planned Verification Tests**:
  * `test_permissions.py::test_viewer_cannot_grant_or_revoke_permissions`: Viewer attempts to add a new user and receives `403 Forbidden`.
  * `test_auth.py::test_registration_cannot_set_admin_role`: User attempting to register with `role: "admin"` is forced to regular role or rejected.

---

### Threat 5: Permission Revocation Failures (Stale Permissions)
* **Description**: A user whose access was revoked continues to view or download a document because permissions were embedded in a long-lived JWT or cached in the application layer.
* **STRIDE Category**: Elevation of Privilege / Information Disclosure.
* **Potential Impact**: High. Revocation is ineffective, violating data protection requirements.
* **Planned Mitigations**:
  * Do **not** bake document-specific access permissions into JWT claims.
  * Verify document permissions against the live MongoDB `permissions` collection on **every** single download or access request.
  * Deleting a permission record immediately and synchronously cuts off subsequent downloads.
* **Planned Verification Tests**:
  * `test_permissions.py::test_revocation_immediately_blocks_download`:
    1. Owner grants Viewer access to document.
    2. Viewer successfully downloads document.
    3. Owner revokes Viewer access.
    4. Viewer immediately attempts another download and receives `403 Forbidden`.

---

### Threat 6: Audit-Log Tampering & Repudiation
* **Description**: An attacker or rogue user performs unauthorized operations and alters or deletes audit records to conceal their trail.
* **STRIDE Category**: Repudiation / Tampering.
* **Potential Impact**: High. Loss of forensic evidence and inability to detect breaches.
* **Planned Mitigations**:
  * Store audit logs in an append-only collection (`audit_logs`).
  * No public or user-facing API endpoints may expose `PUT`, `PATCH`, or `DELETE` methods on audit logs.
  * Log both **successful** and **denied** attempts with timestamp, actor ID, action type, target document ID, client IP, and outcome.
  * Restrict log query access strictly to system Admins (global logs) and Document Owners (logs specific to their documents).
* **Planned Verification Tests**:
  * `test_audit.py::test_unauthorized_access_creates_denied_audit_entry`: Verifies that a `403 Forbidden` attempt records a corresponding audit event.
  * `test_audit.py::test_audit_logs_cannot_be_deleted_via_api`: Asserts no endpoint exists to delete or modify audit entries.

---

### Threat 7: Malicious File Uploads (Path Traversal, Malware, and Resource Exhaustion)
* **Description**: An attacker uploads a file with a malicious filename (e.g., `../../etc/passwd`), an executable script (e.g., `.php`, `.py`, `.html` containing stored XSS), or an excessively large file to cause denial of service.
* **STRIDE Category**: Tampering / Denial of Service.
* **Potential Impact**: Critical. Remote code execution, server compromise, or stored XSS.
* **Planned Mitigations**:
  * Sanitize all uploaded filenames; store files on disk using randomized UUIDs (e.g., `<uuid4>.bin`) rather than original user-supplied filenames.
  * Store the original filename solely in MongoDB document metadata.
  * Enforce maximum upload file size limits (e.g., 25 MB) at the reverse proxy/FastAPI level.
  * Validate allowed MIME types and file extensions.
  * Set `Content-Disposition: attachment; filename="<sanitized_name>"` on download responses to prevent browsers from executing active HTML/JS content inline.
* **Planned Verification Tests**:
  * `test_documents.py::test_path_traversal_filename_sanitized`: Uploading `../../test.txt` stores file safely under UUID.
  * `test_documents.py::test_oversized_file_upload_rejected`: Files exceeding max size return `413 Payload Too Large`.

---

## 3. Summary of Planned Test Suites

| Test File | Focus Area | Key Threat Mitigated |
| :--- | :--- | :--- |
| `tests/test_auth.py` | Registration, login, password hashing, token validation | Threat 3, Threat 4 |
| `tests/test_permissions.py` | RBAC, Viewer vs Owner vs Admin boundaries, instant revocation | Threat 4, Threat 5 |
| `tests/test_isolation.py` | Multi-user document segregation, IDOR prevention | Threat 1, Threat 2 |
| `tests/test_documents.py` | Secure uploads, UUID disk storage, size limits | Threat 7 |
| `tests/test_audit.py` | Verification of allowed & denied audit records, immutability | Threat 6 |
