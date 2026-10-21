import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { getErrorMessage } from '../api/client';
import AlertBanner from '../components/AlertBanner';

export default function RegisterPage({ onNavigateLogin, onRegisterSuccess }) {
  const { register } = useAuth();
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  // Password rules validation
  const hasMinLength = password.length >= 8 && password.length <= 128;
  const hasUpper = /[A-Z]/.test(password);
  const hasLower = /[a-z]/.test(password);
  const hasDigit = /[0-9]/.test(password);
  const passwordsMatch = password && password === confirmPassword;

  const isFormValid = fullName.trim() && email.trim() && hasMinLength && hasUpper && hasLower && hasDigit && passwordsMatch;

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!isFormValid) {
      setError('Please satisfy all password complexity and matching requirements.');
      return;
    }

    setLoading(true);
    setError(null);
    setSuccess(null);

    try {
      await register(email.trim(), fullName.trim(), password);
      setSuccess('Account registered successfully! You may now sign in.');
      setTimeout(() => {
        onRegisterSuccess?.();
      }, 1500);
    } catch (err) {
      setError(getErrorMessage(err, 'Registration failed. The email address might already be in use.'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="container py-5">
      <div className="row justify-content-center">
        <div className="col-12 col-md-9 col-lg-6">
          <div className="card shadow-sm border-0 rounded-4 overflow-hidden">
            <div className="bg-dark text-white p-4 text-center">
              <div className="mb-2">
                <i className="bi bi-person-check-fill text-primary" style={{ fontSize: '3rem' }}></i>
              </div>
              <h4 className="fw-bold mb-1">Create Your TrustVault Account</h4>
              <p className="text-secondary small mb-0">Join the secure access-controlled document vault</p>
            </div>

            <div className="card-body p-4 p-md-5">
              <AlertBanner type="error" message={error} onClose={() => setError(null)} />
              <AlertBanner type="success" message={success} onClose={() => setSuccess(null)} />

              <form onSubmit={handleSubmit}>
                <div className="mb-3">
                  <label className="form-label fw-semibold text-dark">Full Name *</label>
                  <div className="input-group">
                    <span className="input-group-text bg-light border-end-0">
                      <i className="bi bi-person text-muted"></i>
                    </span>
                    <input
                      type="text"
                      className="form-control border-start-0"
                      placeholder="Jane Doe"
                      value={fullName}
                      onChange={(e) => setFullName(e.target.value)}
                      disabled={loading}
                      required
                      autoComplete="name"
                    />
                  </div>
                </div>

                <div className="mb-3">
                  <label className="form-label fw-semibold text-dark">Email Address *</label>
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

                <div className="mb-3">
                  <label className="form-label fw-semibold text-dark">Password *</label>
                  <div className="input-group">
                    <span className="input-group-text bg-light border-end-0">
                      <i className="bi bi-key text-muted"></i>
                    </span>
                    <input
                      type={showPassword ? 'text' : 'password'}
                      className="form-control border-start-0 border-end-0"
                      placeholder="Min. 8 characters with upper, lower, digit"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      disabled={loading}
                      required
                      autoComplete="new-password"
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

                <div className="mb-3">
                  <label className="form-label fw-semibold text-dark">Confirm Password *</label>
                  <div className="input-group">
                    <span className="input-group-text bg-light border-end-0">
                      <i className="bi bi-shield-check text-muted"></i>
                    </span>
                    <input
                      type={showPassword ? 'text' : 'password'}
                      className="form-control border-start-0"
                      placeholder="Re-type your password"
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      disabled={loading}
                      required
                      autoComplete="new-password"
                    />
                  </div>
                </div>

                {/* Password validation indicators */}
                <div className="p-3 bg-light rounded-3 mb-4 small border">
                  <div className="fw-semibold text-dark mb-2">Password Policy Requirements:</div>
                  <div className="row g-2">
                    <div className={`col-6 ${hasMinLength ? 'text-success' : 'text-muted'}`}>
                      <i className={`bi ${hasMinLength ? 'bi-check-circle-fill' : 'bi-circle'} me-1`}></i>
                      8-128 characters
                    </div>
                    <div className={`col-6 ${hasUpper ? 'text-success' : 'text-muted'}`}>
                      <i className={`bi ${hasUpper ? 'bi-check-circle-fill' : 'bi-circle'} me-1`}></i>
                      One uppercase letter
                    </div>
                    <div className={`col-6 ${hasLower ? 'text-success' : 'text-muted'}`}>
                      <i className={`bi ${hasLower ? 'bi-check-circle-fill' : 'bi-circle'} me-1`}></i>
                      One lowercase letter
                    </div>
                    <div className={`col-6 ${hasDigit ? 'text-success' : 'text-muted'}`}>
                      <i className={`bi ${hasDigit ? 'bi-check-circle-fill' : 'bi-circle'} me-1`}></i>
                      One number (0-9)
                    </div>
                    <div className={`col-12 mt-1 ${passwordsMatch ? 'text-success' : 'text-muted'}`}>
                      <i className={`bi ${passwordsMatch ? 'bi-check-circle-fill' : 'bi-circle'} me-1`}></i>
                      Passwords match
                    </div>
                  </div>
                </div>

                <button
                  type="submit"
                  className="btn btn-primary w-100 py-2 fw-semibold d-flex align-items-center justify-content-center shadow-sm"
                  disabled={loading || !isFormValid}
                >
                  {loading ? (
                    <>
                      <span className="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
                      Registering Account...
                    </>
                  ) : (
                    <>
                      <i className="bi bi-person-plus-fill me-2 fs-5"></i>
                      Create Account
                    </>
                  )}
                </button>
              </form>

              <div className="text-center mt-4 pt-3 border-top">
                <span className="text-muted small">Already have an account? </span>
                <button
                  type="button"
                  className="btn btn-link btn-sm p-0 text-decoration-none fw-semibold"
                  onClick={onNavigateLogin}
                >
                  Sign in here
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
