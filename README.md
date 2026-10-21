# TrustVault — Secure Document-Sharing Application

TrustVault is a secure document-sharing web application developed for the **Snovasys Fresher Hiring Challenge 2026**.

It focuses on user authentication, document-level permissions, secure downloads, permission revocation, file validation, and audit logging.

## Project Status

TrustVault has a working React frontend and FastAPI backend.

- **Backend tests:** 166 passed in the latest recorded test run.
- **Frontend:** Vite production build completed successfully.
- **Database:** MongoDB integration configured for development.
- **Security documentation:** Available in `THREATS.md`.
- **Deployment:** Pending final verification and deployment.

Test results describe the local development environment and do not constitute an independent security audit.

## Technology Stack

| Component | Technology |
|---|---|
| Frontend | React, Vite, Bootstrap |
| Backend | Python, FastAPI |
| Database | MongoDB with Motor |
| Authentication | JWT access tokens |
| Password hashing | Argon2id using `pwdlib` |
| Testing | Pytest |
| API documentation | FastAPI and OpenAPI |

## Features

### 1. Authentication

- User registration and login.
- Password hashing using Argon2.
- JWT-based authentication.
- Verification of the current user and account role.
- Server-side authentication for protected endpoints.

### 2. Document Management

- Upload and list documents.
- Download documents through authenticated backend endpoints.
- Manage document metadata.
- Delete documents according to authorization rules.
- Store uploaded files using generated storage filenames.

### 3. Document Sharing and Permissions

- Share documents with other registered users.
- Grant and revoke document permissions.
- Check active permissions during protected document operations.
- Separate document ownership from explicitly granted access.
- List documents owned by the current user and documents shared with them.

### 4. Security Controls

- Server-side authorization checks.
- Protection against unauthorized document access.
- File-type validation.
- Configurable upload-size limits.
- Environment files excluded from version control.
- Audit logging for supported operations.
- Restricted access to the administrative audit-log endpoint.

### 5. Audit Logging

TrustVault records supported security-relevant operations in MongoDB.

Authorized administrators can access the audit-log endpoint. Audit logging helps with reviewing application activity, but the use of MongoDB does not by itself guarantee tamper-proof or immutable audit records.

## Roles and Permissions

### Admin

- Can access the administrative audit-log endpoint.
- Does not automatically receive access to every private document.

### Owner

- Can manage documents they own.
- Can download and delete their own documents.
- Can manage document metadata.
- Can grant and revoke document permissions.

### Viewer

- Can access documents when an active permission grants the required access.
- Cannot perform owner-only operations without the required authorization.

Public registration does not allow users to assign themselves the Admin role.

Actual access is determined by backend authorization checks, not by the frontend interface alone.

## Project Structure

```text
TrustVault/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   └── v1/
│   │   │       └── endpoints/
│   │   ├── core/
│   │   └── models/
│   ├── tests/
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   ├── package.json
│   └── .env.example
├── docs/
│   ├── api-spec.md
│   └── security-model.md
├── README.md
├── THREATS.md
└── PROMPTS.md
```

## Prerequisites

Install the following before running the project:

- Python 3.12 or a compatible Python version.
- Node.js and npm.
- MongoDB access, either a configured MongoDB Atlas deployment or a local MongoDB instance.
- Git.

## Local Setup

### 1. Clone the repository

After the repository is available on GitHub, clone it:

```powershell
git clone <YOUR_PUBLIC_REPOSITORY_URL>
cd TrustVault
```

Replace `<YOUR_PUBLIC_REPOSITORY_URL>` with the actual repository URL.

If you have already downloaded the project, open PowerShell in the project directory instead.

### 2. Configure the backend

From the project root:

```powershell
cd backend
python -m venv .venv
```

Activate the virtual environment:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install the backend dependencies:

```powershell
python -m pip install -r requirements.txt
```

Create your local environment file:

```powershell
Copy-Item .env.example .env
```

Open the environment file:

```powershell
notepad .env
```

Configure the required values for your environment. For example:

```dotenv
APP_ENV=development
SECRET_KEY=replace-with-a-long-random-secret
MONGODB_URI=your-private-mongodb-connection-string
DATABASE_NAME=trustvault
```

These are example settings, not production credentials.

- Generate a strong random secret for `SECRET_KEY`.
- Set `MONGODB_URI` to your own private MongoDB connection string.
- Never commit `.env` or publish its contents.
- Check `.env.example` and the application's settings for any additional required variables.

Start the backend from the `backend` directory:

```powershell
python -m uvicorn app.main:app --reload
```

The backend should be available at:

```text
http://localhost:8000
```

Keep this terminal open while using the application.

### 3. Configure the frontend

Open a second PowerShell terminal and navigate to the frontend directory from the project root:

```powershell
cd frontend
```

Install the frontend dependencies:

```powershell
npm install
```

Create the frontend environment file if it does not already exist:

```powershell
Copy-Item .env.example .env
```

If the file already exists, do not overwrite your existing configuration.

The local API base URL should normally be:

```dotenv
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

Start the frontend:

```powershell
npm run dev
```

Open the local URL displayed by Vite. The default development URL is usually:

```text
http://localhost:5173
```

Keep both the backend and frontend terminals running while testing the application.

## Running the Backend Tests

From the project root, run:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest -q backend\tests
```

The latest recorded result was:

```text
166 passed, 1 warning
```

The warning concerned a Starlette test-client deprecation notice. No tests failed in that run.

Run the tests again after making changes. Test results can change as the code and dependencies change.

## Building the Frontend

From the project root:

```powershell
cd frontend
npm run build
```

A successful Vite build generates production assets in the `frontend/dist` directory.

The generated build directory should not be committed unless the project's deployment process specifically requires it.

## API Documentation

When the backend is running locally, FastAPI provides interactive API documentation at:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

The project also contains API and security documentation under `docs/`.

Use the interactive documentation to review the available endpoints and test them with authorized development accounts.

## Security Considerations

TrustVault uses several application-level security controls, but it should not be assumed to be production-secure solely because the local tests pass.

Before production deployment:

- Use HTTPS.
- Store secrets in the hosting platform's secret-management settings.
- Restrict MongoDB network access and use a database account with the minimum required permissions.
- Confirm that the configured CORS origins match the deployed frontend.
- Ensure uploaded documents are stored privately.
- Use persistent storage or an appropriate private object-storage service.
- Verify authorization and permission revocation against the deployed application.
- Review audit-log access and retention.
- Configure request-size limits, timeouts, and appropriate rate limits.
- Never publish real user passwords, JWT secrets, or database credentials.

See [`THREATS.md`](THREATS.md) for the threat model and security analysis.

## Documentation

- [`THREATS.md`](THREATS.md) — Threat model, security controls, and remaining risks.
- [`PROMPTS.md`](PROMPTS.md) — AI prompts, development assistance, and correction records.
- [`docs/api-spec.md`](docs/api-spec.md) — API specification.
- [`docs/security-model.md`](docs/security-model.md) — Security model and authorization design.

## Deployment Status

Deployment is pending final verification.

Before publishing a live version, configure the backend, frontend, database, secrets, CORS, and persistent document storage for the selected hosting platform.

A successful local run or frontend build does not establish that the deployed application is configured securely.

## Demo Instructions

For a demonstration:

1. Start the backend and frontend.
2. Register or prepare dedicated test accounts.
3. Demonstrate document upload and listing.
4. Show document sharing with another account.
5. Verify that an authorized user can access a shared document.
6. Revoke access and verify that subsequent protected requests are denied.
7. Demonstrate the administrative audit-log interface using an authorized administrator account.

Use only dedicated demo accounts and non-sensitive sample documents. Do not publish real credentials in this repository.

## License

Add the license required by the challenge or your project before distributing the application under an open-source license.