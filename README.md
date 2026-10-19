# TrustVault - Secure Document-Sharing Web Application

> **Project Status**: **Initial Setup & Planning Phase**  
> *Notice: No application code, backend endpoints, or automated tests have been implemented yet. All features listed below are currently planned and marked accordingly.*

---

## 1. Project Purpose

**TrustVault** is a secure document-sharing web application developed as an individual software development assessment. The primary objective of TrustVault is to demonstrate robust security engineering, strict access control, reliable audit trails, and clean software architecture.

Unlike generic file-sharing utilities, TrustVault prioritizes **confidentiality**, **active server-side authorization**, and **instant access revocation**. Documents are never publicly accessible, and permissions are verified on every single operation.

---

## 2. Planned Technology Stack

| Layer | Technology | Purpose |
| :--- | :--- | :--- |
| **Frontend** | React.js (via Vite) | Component-driven user interface with fast client-side rendering |
| **Styling** | Bootstrap 5 | Clean, responsive, and accessible UI layout |
| **Backend** | Python 3.10+ / FastAPI | Asynchronous high-performance RESTful API framework |
| **Database** | MongoDB (with Motor) | Document database for users, document metadata, permissions, and audit logs |
| **Testing** | Pytest & HTTPX | Automated unit, integration, and security regression testing |

---

## 3. Role-Based Access Control (RBAC)

TrustVault is designed around three primary roles:

1. **Admin**:
   - Manages user accounts and system configuration.
   - Has read-only visibility into global audit logs for security oversight.
   - Does *not* have automatic access to private document contents unless explicitly granted.
2. **Owner**:
   - The user who uploads a document.
   - Has full control over their uploaded documents (view, download, share, revoke, delete).
   - Can grant and revoke access to other users.
   - Can inspect document-level audit logs.
3. **Viewer**:
   - A user explicitly granted read/download access to a specific document.
   - Cannot modify document metadata, alter permissions, or re-share the document.
   - Access can be revoked at any time by the Owner.

---

## 4. Intended Features Matrix

All features below are planned and will be marked as implemented only after thorough development and automated verification.

| Feature Area | Planned Feature Description | Status |
| :--- | :--- | :--- |
| **Authentication** | User registration and login using salted Bcrypt password hashing and JWT sessions | `[PLANNED]` |
| **Role Management** | Assignment and enforcement of Admin, Owner, and Viewer roles | `[PLANNED]` |
| **Private File Storage** | Files stored in an isolated filesystem location outside public web access | `[PLANNED]` |
| **Live Permission Check** | Server-side validation of active permissions on every file stream and metadata request | `[PLANNED]` |
| **Instant Revocation** | Immediate invalidation of access when an owner removes a user's permission | `[PLANNED]` |
| **Audit Logging** | Tamper-resistant logging of both successful and denied access attempts | `[PLANNED]` |
| **Cross-User Isolation** | Complete segregation preventing unauthorized users from accessing others' files | `[PLANNED]` |
| **Automated Testing** | Pytest test suite covering authentication, RBAC, access revocation, and isolation | `[PLANNED]` |

---

## 5. Planned Setup Instructions

### Prerequisites
- **Python**: Version 3.10 or higher
- **Node.js**: Version 18 or higher (with npm)
- **MongoDB**: Local MongoDB instance (running on `mongodb://localhost:27017`) or MongoDB Atlas URI
- **Git**: Version 2.x

---

### Step 1: Clone and Inspect the Repository
```bash
git clone <repository-url>
cd TrustVault
```

---

### Step 2: Backend Setup (Planned)
```powershell
# Navigate to the backend directory
cd backend

# Create a virtual environment
python -m venv .venv

# Activate the virtual environment (Windows PowerShell)
.\.venv\Scripts\Activate.ps1

# Upgrade pip and install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Create environment configuration from template
copy .env.example .env
# Edit .env with your local MongoDB connection string and a strong JWT secret

# Run the FastAPI server in development mode
uvicorn app.main:app --reload --port 8000
```

---

### Step 3: Frontend Setup (Planned)
```powershell
# Open a new terminal and navigate to the frontend directory
cd frontend

# Install dependencies
npm install

# Start the Vite development server
npm run dev
```

---

### Step 4: Running Automated Tests (Planned)
```powershell
# In the backend directory with virtual environment activated:
pytest -v
```

---

## 6. Project Documentation Links

- [docs/architecture.md](docs/architecture.md) - System architecture and data flow design
- [docs/security-model.md](docs/security-model.md) - Security model, authorization mechanisms, and policy enforcement
- [docs/api-spec.md](docs/api-spec.md) - Preliminary REST API endpoints specification
- [THREATS.md](THREATS.md) - Threat analysis, mitigations, and planned verification tests
- [PROMPTS.md](PROMPTS.md) - Honest development log tracking AI interactions, challenges, and revisions
