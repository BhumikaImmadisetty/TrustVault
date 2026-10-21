import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { getErrorMessage } from '../api/client';
import AlertBanner from '../components/AlertBanner';

export default function LoginPage({ onNavigateRegister, onLoginSuccess }) {
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!email || !password) {
      setError('Please provide both your email address and password.');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      await login(email.trim(), password);
      onLoginSuccess?.();
    } catch (err) {
      setError(getErrorMessage(err, 'Invalid email or password. Please verify your credentials.'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="container py-5">
      <div className="row justify-content-center">
        <div className="col-12 col-md-8 col-lg-5">
          <div className="card shadow-sm border-0 rounded-4 overflow-hidden">
            <div className="bg-dark text-white p-4 text-center">
              <div className="mb-2">
                <i className="bi bi-shield-lock-fill text-primary" style={{ fontSize: '3rem' }}></i>
              </div>
              <h4 className="fw-bold mb-1">Sign In to TrustVault</h4>
              <p className="text-secondary small mb-0">Secure, end-to-end access-controlled document vault</p>
            </div>

            <div className="card-body p-4 p-md-5">
              <AlertBanner type="error" message={error} onClose={() => setError(null)} />

              <form onSubmit={handleSubmit}>
                <div className="mb-3">
                  <label className="form-label fw-semibold text-dark">Email Address</label>
                  <div className="input-group">
                    <span className="input-group-text bg-light border-end-0">
                      <i className="bi bi-envelope text-muted"></i>
                    </span>
                    <input
                      type="email"
                      className="form-control border-start-0"
                      placeholder="name@example.com"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      disabled={loading}
                      required
                      autoComplete="username"
                    />
                  </div>
                </div>

                <div className="mb-4">
                  <label className="form-label fw-semibold text-dark">Password</label>
                  <div className="input-group">
                    <span className="input-group-text bg-light border-end-0">
                      <i className="bi bi-key text-muted"></i>
                    </span>
                    <input
                      type={showPassword ? 'text' : 'password'}
                      className="form-control border-start-0 border-end-0"
                      placeholder="Enter your password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      disabled={loading}
                      required
                      autoComplete="current-password"
                    />
                    <button
                      type="button"
                      className="btn btn-outline-secondary border-start-0 bg-light text-muted"
                      onClick={() => setShowPassword(!showPassword)}
                      tabIndex="-1"
                    >
                      <i className={`bi ${showPassword ? 'bi-eye-slash' : 'bi-eye'}`}></i>
                    </button>
                  </div>
                </div>

                <button
                  type="submit"
                  className="btn btn-primary w-100 py-2 fw-semibold d-flex align-items-center justify-content-center shadow-sm"
                  disabled={loading}
                >
                  {loading ? (
                    <>
                      <span className="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
                      Authenticating...
                    </>
                  ) : (
                    <>
                      <i className="bi bi-box-arrow-in-right me-2 fs-5"></i>
                      Sign In
                    </>
                  )}
                </button>
              </form>

              <div className="text-center mt-4 pt-3 border-top">
                <span className="text-muted small">Don't have an account yet? </span>
                <button
                  type="button"
                  className="btn btn-link btn-sm p-0 text-decoration-none fw-semibold"
                  onClick={onNavigateRegister}
                >
                  Register here
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
