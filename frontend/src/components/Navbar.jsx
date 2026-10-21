import React from 'react';
import { useAuth } from '../context/AuthContext';

export default function Navbar({ activePage, setActivePage }) {
  const { user, isAuthenticated, isAdmin, logout } = useAuth();

  const getRoleBadge = (role) => {
    switch (role?.toLowerCase()) {
      case 'admin':
        return <span className="badge bg-danger ms-2">Administrator</span>;
      case 'owner':
        return <span className="badge bg-primary ms-2">Owner</span>;
      default:
        return <span className="badge bg-secondary ms-2">{role || 'Viewer'}</span>;
    }
  };

  return (
    <nav className="navbar navbar-expand-lg navbar-dark bg-dark shadow-sm py-3 mb-4 sticky-top border-bottom border-secondary">
      <div className="container-fluid px-lg-5">
        <a
          className="navbar-brand d-flex align-items-center fw-bold fs-4 text-white cursor-pointer"
          onClick={() => setActivePage('dashboard')}
          href="#dashboard"
          style={{ textDecoration: 'none' }}
        >
          <i className="bi bi-shield-lock-fill text-primary me-2 fs-3"></i>
          <span>TrustVault</span>
        </a>

        <button
          className="navbar-toggler"
          type="button"
          data-bs-toggle="collapse"
          data-bs-target="#trustvaultNav"
          aria-controls="trustvaultNav"
          aria-expanded="false"
          aria-label="Toggle navigation"
        >
          <span className="navbar-toggler-icon"></span>
        </button>

        <div className="collapse navbar-collapse" id="trustvaultNav">
          {isAuthenticated ? (
            <>
              <ul className="navbar-nav me-auto mb-2 mb-lg-0 ms-lg-3">
                <li className="nav-item">
                  <button
                    className={`nav-link btn btn-link text-decoration-none px-3 ${
                      activePage === 'dashboard' ? 'active text-white fw-bold' : 'text-light'
                    }`}
                    onClick={() => setActivePage('dashboard')}
                  >
                    <i className="bi bi-folder2-open me-1"></i> Documents
                  </button>
                </li>
                {isAdmin && (
                  <li className="nav-item">
                    <button
                      className={`nav-link btn btn-link text-decoration-none px-3 ${
                        activePage === 'audit' ? 'active text-white fw-bold' : 'text-light'
                      }`}
                      onClick={() => setActivePage('audit')}
                    >
                      <i className="bi bi-journal-text me-1"></i> Audit Trail
                    </button>
                  </li>
                )}
              </ul>

              <div className="d-flex align-items-center ms-auto">
                <div className="text-light me-3 text-end d-none d-md-block">
                  <div className="fw-semibold">
                    {user?.full_name}
                    {getRoleBadge(user?.role)}
                  </div>
                  <small className="text-secondary">{user?.email}</small>
                </div>
                <button
                  className="btn btn-outline-danger btn-sm px-3"
                  onClick={logout}
                  title="Sign out of TrustVault"
                >
                  <i className="bi bi-box-arrow-right me-1"></i> Sign Out
                </button>
              </div>
            </>
          ) : (
            <ul className="navbar-nav ms-auto mb-2 mb-lg-0">
              <li className="nav-item">
                <button
                  className={`btn btn-sm me-2 ${
                    activePage === 'login' ? 'btn-primary' : 'btn-outline-light'
                  }`}
                  onClick={() => setActivePage('login')}
                >
                  Sign In
                </button>
              </li>
              <li className="nav-item">
                <button
                  className={`btn btn-sm ${
                    activePage === 'register' ? 'btn-primary' : 'btn-outline-secondary'
                  }`}
                  onClick={() => setActivePage('register')}
                >
                  Register
                </button>
              </li>
            </ul>
          )}
        </div>
      </div>
    </nav>
  );
}
