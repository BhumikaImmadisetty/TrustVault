# TrustVault — Threat Model & Security Analysis

> **Document Status:** Implemented security controls with ongoing verification
>
> TrustVault is a secure document-sharing application built with FastAPI, MongoDB, and React. This document describes the primary threats to the application, the implemented controls, the available verification tests, and the remaining limitations.
>
> The backend test suite has passed 166 tests in the development environment. This result does not independently establish that every security scenario described in this document has been tested. Refer to the test suite and deployment configuration for the exact verification coverage.

---

## 1. Overview and Threat Modeling Methodology

TrustVault allows authenticated users to upload, organize, access, and share documents. Because documents may contain confidential information, the application must prevent unauthorized access, privilege escalation, insecure downloads, and misuse of file-sharing permissions.

This threat model uses the STRIDE methodology:

- **Spoofing:** An attacker impersonates a legitimate user.
- **Tampering:** An attacker changes documents, permissions, or security records without authorization.
- **Repudiation:** A user denies performing an action, and the system lacks sufficient evidence to investigate it.
- **Information Disclosure:** An attacker obtains documents or metadata they are not authorized to access.
- **Denial of Service:** An attacker consumes excessive application or storage resources.
- **Elevation of Privilege:** A user obtains permissions beyond their assigned role.

### Security objectives

TrustVault aims to:

1. Authenticate users before allowing access to protected endpoints.
2. Enforce document-level authorization on the server.
3. Prevent users from accessing other users' private documents without permission.
4. Apply permission grants and revocations to subsequent access requests.
5. Validate uploaded files and avoid using user-supplied filenames as storage paths.
6. Record important security-relevant operations in audit logs.
7. Restrict administrative operations to appropriately authorized users.
8. Avoid exposing passwords, tokens, database credentials, or internal file paths.
9. Provide tests for authentication, authorization, document operations, and audit behavior.

### Roles and access boundaries

TrustVault uses three application roles:

- **Admin:** Can access administrative functionality, including the audit-log interface. Administrator status does not automatically grant access to every private document.
- **Owner:** Can manage documents they own, including document metadata and sharing permissions.
- **Viewer:** Can access documents when the owner has granted the required active permission.

Document-level permissions are separate from general account roles. Access to a document must be determined by the server, not by a role or document ID supplied by the client.

---

## 2. Threat Catalog, Mitigations, and Verification

The following sections identify the main threats, the controls implemented in the application, and the verification needed to assess each control.

### Threat 1: Unauthorized Document Access (IDOR / Broken Object-Level Authorization)

**STRIDE categories:** Information Disclosure, Elevation of Privilege

**Risk:** High

#### Threat description

An authenticated user attempts to access a document belonging to another user by obtaining or guessing its document ID. If the backend checks only whether the requester is logged in, the requester may be able to read, edit, download, or delete a document without authorization.

#### Implemented controls

- Document authorization is enforced on the server.
- Ownership and document-level permissions are checked before protected operations.
- Read and edit access are checked separately.
- Shared documents are listed only when the requesting user has an applicable active permission.
- Document listing combines documents owned by the user with documents shared with the user, while avoiding duplicate results.
- Deleted documents are excluded from normal document listing.
- The application does not rely solely on a document ID supplied by the frontend to authorize access.

#### Verification

The backend test suite includes document and authorization tests.

Relevant scenarios to verify include:

- User B cannot retrieve private document metadata belonging to User A.
- User B cannot download a private document belonging to User A.
- User B cannot edit or delete User A's document without the required permission.
- A user cannot grant or revoke permissions for a document they do not own.
- Shared documents appear for authorized users but remain unavailable to unauthorized users.

**Verification status:** The backend test suite has passed 166 tests. Confirm individual test names and coverage in `backend/tests` before claiming that every scenario above has a dedicated automated test.

---

### Threat 2: Insecure Downloads and Direct File Exposure

**STRIDE category:** Information Disclosure

**Risk:** High

#### Threat description

If uploaded files are stored in a publicly accessible directory, or if a download endpoint does not recheck permissions, an unauthorized person may retrieve confidential documents without proper authentication.

#### Implemented controls

- Document downloads are handled through an authenticated backend endpoint.
- The backend checks document access before serving a file.
- Uploaded files are stored in the application's storage directory rather than intentionally exposed through a public static-file route.
- Files are stored using generated filenames rather than relying on the original uploaded filename as the disk path.
- Document download requests use the application's authentication and authorization mechanisms.

#### Additional verification

Before production deployment, verify that:

- Unauthenticated download requests are rejected.
- Users without document access cannot download the file.
- A revoked user cannot download the document on a subsequent request.
- Download responses use suitable `Content-Disposition` headers.
- Sensitive file responses use an appropriate cache policy, such as `Cache-Control: no-store`.
- The deployment does not expose the storage directory through a public web server or static-file route.

**Important limitation:** The current development setup uses local file storage. A production deployment must ensure that uploaded documents remain private and that storage persists across application restarts and deployments. A deployment platform's default filesystem may be temporary.

---

### Threat 3: Stolen Credentials and Password Exposure

**STRIDE categories:** Spoofing, Information Disclosure

**Risk:** High

#### Threat description

An attacker obtains a user's password or authentication token, attempts to log in with invalid credentials, or gains access to sensitive configuration values.

#### Implemented controls

- Passwords are hashed using Argon2 through `pwdlib` with its Argon2 support.
- Passwords are not intended to be stored in plaintext.
- Login uses password verification rather than comparing plaintext passwords with stored values.
- Authentication uses signed JWT access tokens.
- Protected endpoints identify the authenticated user through the backend authentication dependency.
- User authentication and account information are retrieved from the database.
- Environment files are excluded from Git through `.gitignore`.
- Example environment files can be shared without publishing actual application secrets.

#### Production requirements

- Use HTTPS/TLS for all production authentication and document traffic.
- Keep the MongoDB connection string and JWT signing secret out of source control.
- Use a strong, randomly generated signing secret.
- Do not publish real credentials in `README.md`, `PROMPTS.md`, screenshots, or demonstration videos.
- Use dedicated demo accounts with non-sensitive test documents.
- Rotate any credentials that may have been accidentally exposed.
- Configure appropriate login rate limits before exposing the application publicly.

#### Verification

Review the authentication tests to confirm coverage of:

- Successful registration and login.
- Rejection of invalid credentials.
- Password hashing and verification.
- Rejection of missing, invalid, or expired authentication tokens.
- Prevention of unauthorized role assignment during registration.

**Verification status:** Argon2-based password hashing and JWT authentication are implemented. Confirm the exact test coverage in `backend/tests` before stating that every scenario above has a dedicated test.

---

### Threat 4: Privilege Escalation and Broken Role-Based Access Control

**STRIDE category:** Elevation of Privilege

**Risk:** High

#### Threat description

A regular user attempts to assign themselves an administrator role, modify another user's document, or perform owner-only operations such as changing sharing permissions.

#### Implemented controls

- Standard registration assigns the normal user role rather than trusting a client-supplied administrator role.
- Protected endpoints use server-side authentication and authorization checks.
- The current user's account and role are checked against database information rather than relying only on role information contained in a JWT.
- Owner-only operations require the requester to own the relevant document.
- Permission-management operations enforce document ownership.
- Audit-log access is restricted to authorized administrators.
- An administrator role does not automatically grant unrestricted access to every private document.

#### Verification

Review the tests for these scenarios:

- A registration request cannot create an administrator account by supplying a privileged role.
- A viewer cannot grant or revoke document permissions.
- A user cannot modify another user's document without the required authorization.
- A non-administrator cannot access the administrative audit endpoint.
- Changes to a user's stored role are reflected in subsequent authenticated requests.

**Verification status:** Server-side role and document authorization controls are implemented. The individual test cases should be confirmed in the repository before being listed as completed.

---

### Threat 5: Permission Revocation Failures and Stale Access

**STRIDE categories:** Information Disclosure, Elevation of Privilege

**Risk:** High

#### Threat description

A user continues to access a document after the owner revokes permission. This may happen when permissions are cached, embedded in a long-lived token, or checked only when a sharing link is first created.

#### Implemented controls

- Document-specific access permissions are stored in the database.
- The backend checks applicable permissions during document access operations.
- Permission-management operations allow an owner to grant and revoke access.
- The authorization layer distinguishes document ownership from explicit read and edit permissions.
- The application does not rely solely on a previously issued JWT to determine document-level access.

#### Verification

Verify the following sequence using two test accounts:

1. The owner uploads a document.
2. The owner grants the second account read access.
3. The second account successfully accesses the shared document.
4. The owner revokes the second account's permission.
5. The second account attempts another protected document request.
6. The backend denies access after revocation.

Also verify that read-only users cannot perform edit operations and that permission changes apply to subsequent requests.

**Verification status:** Live database permission checks are implemented. Test the full grant-and-revoke sequence before claiming that immediate revocation has been independently verified in every access path.

---

### Threat 6: Audit-Log Tampering and Repudiation

**STRIDE categories:** Repudiation, Tampering

**Risk:** High

#### Threat description

A user performs a sensitive operation and later denies it, or an attacker attempts to alter or delete the records used to investigate the activity.

#### Implemented controls

- Audit events are stored in the MongoDB `audit_logs` collection.
- The application records security-relevant document and permission operations.
- Authentication-related events are recorded by the backend.
- Audit events can include information such as the actor, action, target, outcome, timestamp, and request context.
- The application provides an administrative audit endpoint.
- Audit access is restricted through server-side authorization.
- The application does not intentionally provide public audit-log modification or deletion endpoints.

#### Limitations

An audit log stored in the same database is not automatically tamper-proof. A database administrator or attacker with sufficient database privileges may still alter or delete records.

TrustVault should not be described as providing cryptographically tamper-evident or immutable audit logs unless additional protections have been implemented and verified.

For stronger production assurance, consider:

- Restricting database permissions for the application account.
- Sending audit records to a separately controlled logging service.
- Configuring retention and backup policies.
- Monitoring attempts to access or modify audit records.
- Using append-only or cryptographically verifiable storage where required.

#### Verification

Review the audit tests to confirm coverage of:

- Creation of audit events for important document operations.
- Recording of relevant denied operations.
- Rejection of unauthorized requests to read audit records.
- Prevention of unauthorized modification or deletion through the application API.

**Verification status:** Audit logging and an administrator-only audit interface are implemented. The exact coverage of denied operations and the protection against database-level tampering must be assessed separately.

---

### Threat 7: Malicious File Uploads, Path Traversal, and Resource Exhaustion

**STRIDE categories:** Tampering, Denial of Service, Information Disclosure

**Risk:** High

#### Threat description

An attacker uploads a file with a malicious filename, an unsupported or misleading file type, or a file that consumes excessive storage or processing resources.

Examples include path-traversal filenames, executable files, misleading extensions, and oversized uploads.

#### Implemented controls

- The backend includes file-validation logic for supported file types.
- Upload handling uses generated storage filenames rather than using the original filename directly as the storage path.
- The original filename is retained as document metadata where required.
- A configurable maximum upload size is defined in application settings.
- Document authorization is enforced independently of the uploaded filename.
- The backend handles document storage separately from the public frontend.

#### Additional verification and production requirements

Verify that:

- Path-traversal filenames cannot write files outside the intended storage directory.
- Unsupported file types are rejected.
- Oversized uploads are rejected without consuming excessive memory or disk space.
- Download responses treat files as attachments where appropriate.
- User-supplied filenames are safely handled in HTTP headers and frontend rendering.
- The production reverse proxy or hosting platform enforces suitable request-size and timeout limits.

File signature checks help identify file formats but do not guarantee that a file is free of malware. If TrustVault will accept sensitive or untrusted files in production, consider malware scanning and additional content-disarm controls appropriate to the deployment.

**Verification status:** File-validation logic and configurable upload limits are implemented. Confirm the exact supported formats, upload-size behavior, and corresponding tests before making stronger security claims.

---

## 3. Additional Security Considerations

### 3.1 Database Availability and Failure Handling

TrustVault depends on MongoDB for account information, document metadata, permissions, and audit records.

Database failures must not cause the application to grant access by default.

Security expectations:

- Authorization checks must fail closed when required permission data cannot be retrieved.
- A database error must not be interpreted as proof that a user has access.
- The application should return an appropriate error when a required database operation cannot be completed.
- Production startup and health checks should make database connectivity failures visible to operators.
- Database credentials should have only the permissions required by the application.

Review startup error handling before deployment to ensure the application does not silently report readiness when required database initialization has failed.

### 3.2 Secret Management

Application secrets must not be committed to Git.

Security expectations:

- Keep `.env` files out of version control.
- Commit example configuration files without real credentials.
- Use a strong, random JWT signing secret.
- Store production secrets in the deployment platform's secret-management settings.
- Use a dedicated MongoDB application account with the minimum required database permissions.
- Never print or share database connection strings, signing secrets, or real account passwords in logs or public documentation.

### 3.3 Deployment and File Storage

The development environment uses local file storage and a MongoDB database.

Before production deployment:

- Confirm that the storage location is private and persistent.
- Do not expose uploaded files through a public static directory.
- Restrict database network access to trusted sources.
- Configure the correct production frontend origin in CORS settings.
- Use HTTPS.
- Verify that the application's database and storage configuration match the deployment environment.
- Test authorization and file downloads against the deployed application, not only on localhost.

### 3.4 Security Testing and Review

Automated tests provide evidence that specific application behavior works under tested conditions. They do not prove that an application is completely secure.

TrustVault's security review should include:

- Authentication and token validation.
- Horizontal access control between users.
- Vertical access control between roles.
- Document sharing and permission revocation.
- Upload validation and file-size enforcement.
- Audit event creation and access control.
- Database failure handling.
- Configuration and secret-management review.
- Verification of the deployed application's security behavior.

---

## 4. Automated Test Coverage

The backend test suite is located in `backend/tests`.

The current development test run completed with:

`166 passed, 1 warning`

This is a snapshot of the test suite at the time it was run. Re-run the suite after significant code changes and before submitting the project.

The following table describes the security areas that should be covered. It is a coverage guide, not a claim that files or test functions with every listed name already exist.

| Test area | Security behavior to verify | Related threats |
|---|---|---|
| Authentication tests | Registration, login, password hashing, token validation | Threat 3, Threat 4 |
| Authorization tests | Owner, viewer, and administrator access boundaries | Threat 1, Threat 4 |
| Document tests | Upload, listing, download, update, delete, and sharing permissions | Threat 1, Threat 2, Threat 5, Threat 7 |
| Permission tests | Grant, revoke, and enforcement of active permissions | Threat 4, Threat 5 |
| Audit tests | Audit event creation and restricted access to audit records | Threat 6 |
| Database failure tests | Safe handling of database errors during protected operations | Threat 1, Threat 4, Threat 5 |
| Deployment checks | HTTPS, CORS, secrets, persistent storage, and database access restrictions | Threats 2, 3, 6, 7 |

### Running the backend tests

From the project root in PowerShell:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest -q backend\tests
```

To review the test files:

```powershell
Get-ChildItem backend\tests
```

To run the frontend production build:

```powershell
cd frontend
npm run build
```

---

## 5. Security Status Summary

| Security area | Current status |
|---|---|
| Password hashing | Argon2-based hashing implemented |
| JWT authentication | Implemented |
| Current-user verification | Implemented |
| Server-side document authorization | Implemented |
| Document sharing and permission management | Implemented |
| Shared-document listing | Implemented |
| File validation | Implemented; review supported formats and edge cases |
| Audit logging | Implemented; verify coverage for all sensitive and denied operations |
| Administrator audit interface | Implemented |
| Backend automated tests | 166 tests passed in the recorded development run |
| Frontend production build | Build succeeded in the recorded development run |
| Production deployment | Requires deployment-specific configuration and verification |
| Persistent production file storage | Must be confirmed for the chosen hosting platform |
| Tamper-evident audit storage | Not claimed |
| Complete production security audit | Not claimed |

---

## 6. Conclusion

TrustVault implements authentication, server-side document authorization, document-level sharing permissions, file-validation logic, and audit logging to reduce common risks in secure document-sharing applications.

The primary security principle is that authentication alone does not grant access to every document. The backend must verify the user's current identity, role, ownership, and applicable document permissions before performing a protected operation.

The recorded automated test results provide useful evidence of correctness for the tested scenarios. Additional review of deployment configuration, storage persistence, audit-log protection, and production security settings is required before the application should be considered production-ready.

This threat model is intended to remain a living document. Update it when security controls change, new risks are identified, or additional tests and deployment protections are verified.