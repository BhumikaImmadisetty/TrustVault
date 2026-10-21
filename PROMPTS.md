# TrustVault - Development & AI Interaction Log

> **Purpose**: This file serves as an honest, chronological record of interactions, prompts, AI assistance, issues encountered, corrections applied, and corresponding Git commits throughout the development of TrustVault.
>
> **Integrity Policy**:
> * Do not fabricate prompts, outputs, or test results.
> * Document both successful suggestions and failures/misdirections.
> * Record actual code corrections, human interventions, and manual adjustments.
> * Maintain a 1-to-1 linkage between logged milestones and Git commits where applicable.

---

## Log Entry Template

Use the following Markdown format for each new development session or distinct task:

```markdown
### Entry [Number]: [Task Title]
* **Date**: YYYY-MM-DD
* **Task Description**: What specific feature, test, or refactor was addressed.
* **User Prompt**: Exact or summarized prompt given to the AI assistant.
* **AI Output / Suggestion**: Summary of the code, structure, or guidance suggested by the AI.
* **Issues / Limitations Encountered**: Any errors, invalid assumptions, security oversights, or bugs found in the output.
* **Correction / Human Intervention Made**: How the issue was resolved or how the code was modified to meet requirements.
* **Related Commit**: Git commit hash (or branch reference) reflecting the final state.
```

---

## Development Log Entries

### Entry 1: Project Repository Initialization & Foundational Documentation
* **Date**: 2026-10-19
* **Task Description**: Initialize project Git repository and create foundational planning documentation (`.gitignore`, `README.md`, `THREATS.md`, `PROMPTS.md`, and `docs/` specifications).
* **User Prompt**:
  > "First, inspect the current workspace and propose a clean project folder structure for the frontend, backend, database setup, tests, and documentation. ... Please create only the following files and folders: 1. .gitignore 2. README.md 3. THREATS.md 4. PROMPTS.md 5. docs/architecture.md 6. docs/security-model.md 7. docs/api-spec.md ... Do not create fake test results or claim any security feature is already implemented. Do not create the backend or frontend code yet. Do not overwrite existing files without checking them first. Explain which files you created and why."
* **AI Output / Suggestion**:
  * Proposed clean modular project structure separating `backend/`, `frontend/`, `docs/`, and `tests/`.
  * Generated security-focused `.gitignore` excluding secrets, virtual environments, cache files, node modules, and uploaded documents.
  * Generated documentation specifying planned tech stack (React + Vite, Bootstrap, FastAPI, MongoDB, Pytest) and explicitly marking all features as `[PLANNED]`.
  * Created comprehensive threat model (`THREATS.md`) and development log template (`PROMPTS.md`).
* **Issues / Limitations Encountered**: None at this stage. Workspace was confirmed empty prior to file generation.
* **Correction / Human Intervention Made**: Verified all features are marked strictly as planned and avoided generating placeholder implementation code prematurely.
* **Related Commit**: Initial commit (pending).

---

### Entry 2: Backend Configuration Setup & Environment Isolation
* **Date**: 2026-10-19
* **Task Description**: Configure backend settings management with `pydantic-settings`, initialize backend packages, configure environment template (`.env.example`), and ensure strict gitignore exclusion of secret files.
* **User Prompt**:
  > "We are developing the TrustVault backend using Python 3.12, FastAPI, MongoDB, and Pytest. ... Please perform only the following tasks: 1. Inspect the existing backend folder and root .gitignore before making changes. 2. Create backend/.env.example with placeholder settings ... 3. Do not create a real .env file or insert actual credentials. 4. Update the root .gitignore if needed so that .env files are ignored, while .env.example remains trackable. 5. Create backend/app/__init__.py and backend/app/core/__init__.py ... 6. Create backend/app/core/config.py using pydantic-settings ... Keep development defaults safe and do not print secrets. 7. Do not connect to MongoDB yet. 8. Do not implement authentication or API endpoints yet. 9. Explain each file created or changed and provide a simple way to verify the configuration without exposing secrets."
* **AI Output / Suggestion**:
  * Updated `.gitignore` to explicitly preserve `!**/.env.example` while ignoring all local `.env` files in any directory.
  * Created `backend/.env.example` with the 8 specified parameters.
  * Initialized `backend/app/__init__.py` and `backend/app/core/__init__.py`.
  * Implemented `backend/app/core/config.py` using `pydantic-settings.BaseSettings`, configured `Field(..., repr=False)` for `SECRET_KEY` to prevent credential exposure in logs/traces, and added a `get_safe_summary()` method masking sensitive values.
* **Issues / Limitations Encountered**: None. Verified using `python -c` that `repr(settings)` excludes `SECRET_KEY` and verified with `git check-ignore` that `backend/.env` is ignored while `backend/.env.example` is trackable.
* **Correction / Human Intervention Made**: Confirmed no database connection or API endpoints were added prematurely.
* **Related Commit**: Pending.

---

### Entry 3: Asynchronous MongoDB Connector Implementation & Testing
* **Date**: 2026-10-19
* **Task Description**: Implement asynchronous MongoDB connection manager (`backend/app/core/database.py`) using Motor, implement non-blocking ping verification with bounded timeout and safe error logging, add unit tests with mocks, and verify connectivity against live MongoDB server.
* **User Prompt**:
  > "We are continuing the TrustVault project. The backend uses Python 3.12, FastAPI, Pydantic Settings, and Motor. The configuration file is already present at backend/app/core/config.py. Before changing anything, inspect the existing configuration and installed package versions. Please implement only the MongoDB connection module at backend/app/core/database.py. ... 1. Use the existing settings object ... 2. Create an asynchronous MongoDB client using Motor ... 3. Use the configured MONGODB_URI and DATABASE_NAME ... 4. Implement an asynchronous function to check the database connection using MongoDB ping ... 5. Provide a clean way to close the MongoDB client during application shutdown ... 6. Do not print the connection string, credentials, or SECRET_KEY ... 7. Handle connection errors safely ... 8. Do not create authentication routes, user models, or document endpoints yet ... 9. Do not claim the connection is successful until an actual connection test passes ... 10. Add a small automated test for the database module where practical, using a mock rather than requiring a live MongoDB server. ... 11. Update PROMPTS.md ... 12. Do not overwrite existing files without checking them first. Explain how to test the connector and distinguish a successful mock test from a successful connection to a real MongoDB server."
* **AI Output / Suggestion**:
  * Inspected `.venv` packages: confirmed Python 3.12.7, `motor==3.7.1`, `pymongo==4.19.0`, `pytest==9.1.1`, and `pytest-asyncio==1.4.0`.
  * Created `backend/app/core/database.py` with `DatabaseManager` providing lazy client initialization, bounded `serverSelectionTimeoutMS=2000`, safe sanitized exception catching (no URI or credential logging), and explicit `.close_connection()` cleanup.
  * Created `backend/pytest.ini` with `asyncio_mode = auto` and `testpaths = tests`.
  * Created `backend/tests/test_database.py` with 4 isolated unit tests using `unittest.mock.AsyncMock` verifying: successful ping, timeout failure handling, driver error handling, and client cleanup.
  * Executed unit tests with `pytest -v` (4 passed in 1.66s).
  * Executed live connectivity test via `check_db_connection()`, which connected to the local MongoDB instance on port 27017 and returned `True`.
* **Issues / Limitations Encountered**: None. Lazy initialization prevented unhandled loop attachment warnings during testing.
* **Correction / Human Intervention Made**: Distinguished mock test execution (which tests the module's control flow and error trapping) from live socket connection execution (which tests physical database reachability).
* **Related Commit**: Pending.

---

### Entry 4: User Schemas, Argon2 Password Security & Validation Tests
* **Date**: 2026-10-19
* **Task Description**: Define user data schemas (`backend/app/models/user.py`), implement password hashing and verification using `pwdlib[argon2]` (`backend/app/core/security.py`), enforce role boundaries and password hash isolation, and create automated test suite (`backend/tests/test_auth_security.py`).
* **User Prompt**:
  > "We are continuing the TrustVault project. ... Implement only the user schemas and password security helpers. Part A — User models: 1. Create app/models/__init__.py ... 2. Create app/models/user.py using Pydantic. 3. Define exactly three supported roles: admin, owner, and viewer. 4. Define appropriate user input and response schemas. 5. Include fields such as user ID, full name, email, role, active status, and timestamps ... 6. Validate and normalize email addresses. 7. Never include password hashes in public user response schemas. 8. Do not allow public registration to assign the admin role. Part B — Password security: 1. Create app/core/security.py. 2. Use pwdlib with Argon2 ... 3. Never store plaintext passwords. 4. Reject empty or excessively long passwords safely. 5. Do not log passwords, hashes, secret keys, or tokens. 6. Keep authentication token generation out of scope for this step. Part C — Automated tests: 1. Create tests for password hashing and verification. ... 6. Use the existing testing conventions and run the complete test suite. Update PROMPTS.md with the actual work performed and any real issues encountered."
* **AI Output / Suggestion**:
  * Created `backend/app/models/__init__.py` and `backend/app/models/user.py` defining `UserRole` (`admin`, `owner`, `viewer`), `UserRegister`, `UserResponse`, `UserInDB`, and `UserRoleUpdate`.
  * Implemented `backend/app/core/security.py` using `pwdlib.PasswordHash.recommended()` for Argon2id hashing and verification, adding length constraints (8 to 128 characters) and timing/safe closed-failure handling.
  * Created `backend/tests/test_auth_security.py` with 13 comprehensive test cases.
* **Issues / Limitations Encountered**:
  * During the initial test run, `from pydantic import EmailStr` raised an `ImportError: email-validator is not installed` because the virtual environment did not include the optional `email-validator` dependency.
* **Correction / Human Intervention Made**:
  * Replaced `EmailStr` in `app/models/user.py` with a self-contained RFC-compliant regex validator and normalizer (`validate_and_normalize_email_str`) that strips whitespace, forces lowercase, and validates email syntax without external dependencies.
  * Re-ran `pytest -v`: all 17 tests (13 security/model tests + 4 database tests) passed cleanly in 2.24 seconds.
* **Related Commit**: Pending.

---

### Entry 5: JWT Access-Token Generation, Verification & Security Tests
* **Date**: 2026-10-19
* **Task Description**: Implement JWT access-token creation and verification in `backend/app/core/security.py` using PyJWT, integrate `SECRET_KEY` from configuration with explicit `HS256` signing, validate required claims (`sub`, `iat`, `exp`), ensure roles in tokens do not bypass live server-side authorization (Requirement 8), and add 8 unit tests in `backend/tests/test_auth_security.py`.
* **User Prompt**:
  > "Continue developing TrustVault. ... Implement JWT access-token creation and verification in app/core/security.py, preserving the existing password security functions. Requirements: 1. Use the already installed PyJWT package. 2. Read the signing secret from the existing settings object. 3. Do not hardcode a real secret or print secret values. 4. Use an explicit signing algorithm, HS256. 5. Include the user ID as the token subject and include issued-at and expiration claims. 6. Validate the token signature, expiry, and required claims during decoding. 7. Reject malformed, expired, tampered, or incorrectly signed tokens safely. 8. Do not treat a role claim inside a token as the final authority for permissions. Current user status and permissions must be checked server-side on protected requests. 9. Do not implement login or registration endpoints yet. 10. Add automated tests for valid tokens, expired tokens, tampered tokens, missing required claims, and invalid tokens. 11. Ensure tests use a dedicated test secret and never print real secrets. 12. Update PROMPTS.md with the actual work performed and real issues encountered. 13. Run the full test suite and report the actual result. 14. Do not overwrite unrelated files. Important: inspect how the existing settings load SECRET_KEY before implementing this. If the current development secret is only a placeholder, explain that a real secret must be configured before running the application outside tests."
* **AI Output / Suggestion**:
  * Inspected `backend/app/core/config.py`: noted `SECRET_KEY` defaults to a 48-character development placeholder (`replace-with-a-long-random-secret-before-running`) with `repr=False`. Explained that this placeholder must be replaced with a high-entropy secret in production `.env`.
  * Updated `backend/app/core/security.py` preserving password hashing functions and adding `create_access_token()` and `decode_access_token()` using `PyJWT` with explicit `ALGORITHM = "HS256"`.
  * Defined custom security exceptions: `TokenSecurityError`, `TokenExpiredError`, and `InvalidTokenError`.
  * Enforced mandatory validation of `sub`, `iat`, and `exp` claims with signature verification.
  * Added explicit architectural guard comments stating token claims are informational and live permissions must be checked on every request.
  * Added 8 new automated test cases to `backend/tests/test_auth_security.py` using dedicated 32+ byte test secrets (`TEST_SECRET_A`, `TEST_SECRET_B`).
  * Ran full pytest suite: all 25 tests passed in 2.42 seconds.
* **Issues / Limitations Encountered**: None. PyJWT key length recommendations (minimum 32 bytes for HS256) were respected in both default settings and test fixtures to prevent insecure key warnings.
* **Correction / Human Intervention Made**: Avoided creating authentication endpoints or modifying the database module.
* **Related Commit**: Pending.

---

### Entry 6: User Registration and Login API Implementation & Testing
* **Date**: 2026-10-19
* **Task Description**: Implement user registration (`POST /auth/register`) and user login (`POST /auth/login`) API endpoints in FastAPI, enforce email normalization, least-privilege default role assignment, duplicate rejection, and generic authentication errors. Create `backend/app/main.py`, `backend/app/api/deps.py`, `backend/app/api/v1/endpoints/auth.py`, `backend/app/api/v1/router.py`, and comprehensive test suite (`backend/tests/test_auth_api.py`).
* **User Prompt**:
  > "Continue developing my TrustVault project. ... TASK: Implement user registration and login APIs. ... REQUIREMENTS: A. Registration: Create POST /auth/register. Accept a validated email and password. Normalize the email consistently. Reject duplicate email addresses. Never accept an admin role from public registration. Assign the least-privileged appropriate default role. Hash passwords using the existing Argon2 function. Never store plaintext passwords. Never return password hashes in API responses. Handle duplicate registration safely. B. Login: Create POST /auth/login. Verify the submitted password against the stored Argon2 hash. Return a JWT access token after successful login. Use the existing JWT functions and configuration. Return a generic authentication error for incorrect email or password. Do not expose password hashes, secrets, or internal errors. Do not log passwords or tokens. C. Security: Never hardcode a real secret. Do not trust a role supplied by the client. Use the existing MongoDB database helper. Handle database errors safely. Follow the existing project structure and configuration. Do not implement document sharing or permissions yet. D. Tests: Add tests for: Successful registration. Password stored as a hash. Duplicate email rejected. Public registration cannot create an admin. Successful login. Incorrect password rejected. Unknown email rejected. Password hash never returned. Database failures handled safely. Use mocks for database-dependent tests where appropriate. Do not require a running MongoDB server for unit tests. E. Documentation: Update API documentation with request and response examples, authentication requirements, and error responses. Append a truthful dated entry to PROMPTS.md describing the actual prompt, changes, test results, and any real errors encountered."
* **AI Output / Suggestion**:
  * Updated `backend/app/models/user.py` and `backend/app/models/__init__.py` with `UserLogin` and `TokenResponse` models.
  * Created `backend/app/api/deps.py` with `get_database()` dependency for easy test overrides.
  * Implemented `backend/app/api/v1/endpoints/auth.py` with `register` and `login` route handlers.
  * Created `backend/app/api/v1/router.py` aggregating API v1 endpoints.
  * Created `backend/app/main.py` configuring FastAPI lifespan (closing DB on shutdown) and mounting `/api/v1` and `/auth` routes.
  * Created `backend/tests/test_auth_api.py` with 11 automated test cases using `InMemoryMockDatabase` and `TestClient`.
  * Updated `docs/api-spec.md` with implemented request/response schemas, role constraints, and error codes.
  * Executed `pytest -v`: all 36 tests (11 API tests + 21 security/model tests + 4 database tests) passed in 6.79 seconds.
* **Issues / Limitations Encountered**: None. A Starlette deprecation warning regarding `httpx` vs `httpx2` in `fastapi.testclient` was noted during pytest execution, but did not affect test correctness or assertions.
* **Correction / Human Intervention Made**: Both `/api/v1/auth/register` and root `/auth/register` (and login counterparts) were mounted to support either URL convention without breaking client assumptions.
* **Related Commit**: Pending.

---

### Entry 7: Secure Authentication Dependency (`get_current_user`) Implementation & Verification
* **Date**: 2026-10-19
* **Task Description**: Implement `get_current_user` dependency in `backend/app/api/deps.py`, extract and validate Bearer tokens, enforce live MongoDB user lookup, enforce Requirement 8 (resolving role and active status from the database rather than trusting token claims), add `GET /api/v1/auth/me` endpoint, and create automated test suite (`backend/tests/test_auth_deps.py`).
* **User Prompt**:
  > "Continue developing my TrustVault project. ... TASK: Implement secure authentication for protected API endpoints. ... REQUIREMENTS: 1. Implement get_current_user in app/api/deps.py. 2. Extract the Bearer token using FastAPI's security utilities. 3. Decode and verify the JWT using the existing security module. 4. Reject missing, malformed, expired, and invalid tokens. 5. Extract the user identifier from the verified token subject. 6. Retrieve the current user record from MongoDB. 7. Reject tokens whose subject does not correspond to a valid current user. 8. Do not trust a role claim from the token as the authority. Read the current role and account status from the database. 9. Do not return password hashes in API responses or errors. 10. Fail safely if the database is unavailable. 11. Keep authentication separate from authorization. Do not implement document-sharing permissions yet. 12. Do not log tokens, passwords, or secrets. TESTS: Add automated tests for: Missing Authorization header. Malformed Bearer token. Expired token. Tampered token. Valid token for an existing user. Token for a nonexistent user. Database unavailable. Current role is taken from the database rather than trusting a role claim supplied in the token. Use mocked database dependencies where appropriate so unit tests do not require a running MongoDB server. DOCUMENTATION: Update docs/api-spec.md with authentication requirements. Add a truthful dated entry to PROMPTS.md describing the actual prompt, changes, test results, and any genuine errors encountered. VERIFICATION: Run the complete test suite using backend/.venv. Report actual passed, failed, and errored test counts. List all created and modified files. Explain how to test the authentication dependency locally."
* **AI Output / Suggestion**:
  * Implemented `get_current_user` in `backend/app/api/deps.py` with `HTTPBearer(auto_error=False)` and direct `Request.headers` inspection.
  * Added `GET /api/v1/auth/me` endpoint in `backend/app/api/v1/endpoints/auth.py` returning `UserResponse`.
  * Created `backend/tests/test_auth_deps.py` with 9 automated test cases covering: missing header, non-Bearer schemes, empty tokens, expired tokens, tampered signatures, existing user resolution, nonexistent users, deactivated users, database failures (503), and live database role resolution (Requirement 8).
  * Updated `docs/api-spec.md` with section 1.3 documenting `GET /api/v1/auth/me` and marked the endpoint as `[IMPLEMENTED]`.
* **Issues / Limitations Encountered**:
  * During initial testing of `test_malformed_bearer_token`, supplying `Authorization: Basic ...` resulted in `HTTPBearer(auto_error=False)` yielding `None`, which triggered the generic "Authentication credentials were not provided" error rather than distinguishing the invalid authentication scheme.
* **Correction / Human Intervention Made**:
  * Updated `get_current_user` in `backend/app/api/deps.py` to inspect `request.headers.get("Authorization")` directly. This enables distinct handling for missing headers vs. non-Bearer schemes vs. empty parameter tokens.
  * Re-ran `pytest -v`: all 45 tests (9 deps tests + 11 auth API tests + 21 security/model tests + 4 database tests) passed in 5.81 seconds.
* **Related Commit**: Pending.

---

### Entry 8: Document Metadata Models, Private Storage & Authenticated Upload/Listing
* **Date**: 2026-10-19
* **Task Description**: Implement Stage 1 of document management — Pydantic document models, private server-side file storage with UUID-based filenames, authenticated document upload (`POST /api/v1/documents/upload`) and listing (`GET /api/v1/documents/`) endpoints, and a comprehensive automated test suite (`backend/tests/test_documents.py`).
* **User Prompt**:
  > "Continue developing TrustVault. ... TASK: Implement the first stage of secure document management: document metadata models, private local file storage, and authenticated document upload and listing. ... A. Document metadata: Create a document model ... B. Private storage: ... generate a UUID-based server-side filename ... never use the original filename as the storage path ... do not return the storage path in any API response ... create a per-owner subdirectory ... C. Upload endpoint: POST /api/v1/documents/upload ... D. Listing endpoint: GET /api/v1/documents/ ... E. Tests: ... storage_path excluded from all responses ... unauthenticated access rejected ... disallowed MIME type rejected ... empty file rejected ... database failure returns 503 ... pagination ..."
* **AI Output / Suggestion**:
  * Created `backend/app/models/document.py` defining `DocumentStatus` enum (`active`, `archived`, `deleted`), `DocumentInDB` (internal, includes `storage_path`), `DocumentResponse` (public, excludes `storage_path`), and `DocumentListResponse`.
  * Created `backend/app/api/v1/endpoints/documents.py` implementing:
    * `POST /api/v1/documents/upload`: reads file up to `MAX_UPLOAD_SIZE_MB + 1` bytes, rejects empty files (`400`), rejects disallowed MIME types against a server-side allowlist (`415`), stores file under UUID-based filename in per-owner subdirectory, inserts metadata to MongoDB, rolls back stored file on DB failure, never returns `storage_path`.
    * `GET /api/v1/documents/`: scoped to `owner_id == current_user.id`, excludes `status: deleted`, supports `skip`/`limit` pagination, sorted by `created_at` descending, never returns `storage_path`.
  * Updated `backend/app/api/v1/router.py` to mount `documents.router` at prefix `/documents`.
  * Created `backend/tests/test_documents.py` with 17 automated tests covering: valid PDF upload, `storage_path` exclusion from both upload and listing responses, correct `owner_id` attribution, optional description, disallowed MIME type rejection, empty file rejection, unauthenticated access rejection (upload and listing), DB failure on upload (`503`), physical file storage verification, UUID storage filename verification (path traversal sequence `../../../etc/passwd` in filename does not reach filesystem), empty listing, owner-scoped listing, soft-deleted document exclusion, `storage_path` exclusion from listing, pagination, unauthenticated listing rejection, DB failure on listing (`503`).
  * Ran full test suite: **62 tests passed, 0 failed** (command: `.venv\Scripts\python.exe -m pytest tests/ -v --tb=short`). Execution time: 7.32 seconds.
* **Issues / Limitations Encountered**: None. All 17 new tests passed on the first run.
* **Correction / Human Intervention Made**: None required.
* **Related Commit**: Pending.

---

### Entry 9: Documentation Review & Correction (api-spec.md, security-model.md, PROMPTS.md)
* **Date**: 2026-10-19
* **Task Description**: Review `docs/api-spec.md`, `docs/security-model.md`, and `PROMPTS.md` against the actual Entry 8 implementation. Correct inaccuracies and add missing information without touching any Python code.
* **User Prompt**:
  > "Review the document-management implementation you just completed. Do not modify the Python code yet. Check whether docs/api-spec.md, docs/security-model.md, and PROMPTS.md have been updated to accurately describe the new document model, upload/list endpoints, ownership restrictions, private storage, validation, and tests. Update any missing documentation. Do not mark sharing, downloads, deletion, or audit logging as implemented if those features do not exist yet. Record only actual work and actual test results in PROMPTS.md."
* **AI Output / Suggestion**:
  * **`docs/api-spec.md`**: Corrected document endpoint table — `POST /api/v1/documents/upload` and `GET /api/v1/documents/` marked `[IMPLEMENTED]`. Added detailed sections 2.1 and 2.2 with request/response examples, MIME allowlist, storage security notes, pagination parameters, and error code tables. Added subsections 2.3–2.5 as `[PLANNED]` stubs for get-by-id, download, and delete. Added `415`, `422`, `409`, and `500` to the HTTP status conventions table. Corrected the status banner from "all planned" to "partially implemented".
  * **`docs/security-model.md`**: Corrected three factual errors present since Entry 4:
    1. Section 2.1 stated "salted bcrypt" — corrected to **Argon2id via pwdlib** (the actual library used since Entry 4).
    2. Section 2.2 JWT payload example included a `role` claim — removed, as the actual implementation puts only `sub`, `iat`, and `exp` in the token.
    3. Section 2.2 stated "30–60 minute" token lifetime — corrected to **15 minutes** (the actual `ACCESS_TOKEN_EXPIRE_MINUTES` default).
    * Added new **Section 4: Private Document Storage Security** covering storage location, UUID filename design, per-owner directories, `storage_path` exclusion from responses, MIME allowlist, size/empty validation, orphan rollback, and owner-scoped listing. Renumbered former sections 4 and 5 to 5 and 6 and marked them `[PLANNED]`.
  * **`PROMPTS.md`**: Added Entry 8 and Entry 9 with accurate descriptions of actual work performed and actual test results.
* **Issues / Limitations Encountered**:
  * `docs/security-model.md` contained three inaccuracies that had been present since Entry 4 (incorrect hashing algorithm, incorrect JWT claims, incorrect token lifetime). These were not caught until this explicit documentation review.
* **Correction / Human Intervention Made**: All three inaccuracies were corrected in this session. Future documentation entries should be written immediately after implementation to avoid drift.
* **Related Commit**: Pending.

---

*(Additional entries will be added chronologically as each development step is executed.)*
