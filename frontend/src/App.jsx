import React, { useState, useEffect } from 'react';
import { useAuth } from './context/AuthContext';
import Navbar from './components/Navbar';
import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import DashboardPage from './pages/DashboardPage';
import AuditPage from './pages/AuditPage';

export default function App() {
  const { isAuthenticated, loading, isAdmin } = useAuth();
  const [activePage, setActivePage] = useState('dashboard');

  useEffect(() => {
    if (!isAuthenticated) {
      if (activePage !== 'register') {
        setActivePage('login');
      }
    } else {
      if (activePage === 'login' || activePage === 'register') {
        setActivePage('dashboard');
      }
    }
  }, [isAuthenticated, activePage]);

  if (loading) {
    return (
      <div className="d-flex flex-column align-items-center justify-content-center vh-100 bg-light">
        <div className="spinner-border text-primary mb-3" style={{ width: '3rem', height: '3rem' }} role="status">
          <span className="visually-hidden">Loading...</span>
        </div>
        <div className="text-secondary fw-semibold">Connecting to TrustVault Secure Enclave...</div>
      </div>
    );
  }

  return (
    <div className="min-vh-100 d-flex flex-column bg-light">
      <Navbar activePage={activePage} setActivePage={setActivePage} />

      <main className="flex-grow-1">
        {!isAuthenticated ? (
          activePage === 'register' ? (
            <RegisterPage
              onNavigateLogin={() => setActivePage('login')}
              onRegisterSuccess={() => setActivePage('login')}
            />
          ) : (
            <LoginPage
              onNavigateRegister={() => setActivePage('register')}
              onLoginSuccess={() => setActivePage('dashboard')}
            />
          )
        ) : activePage === 'audit' && isAdmin ? (
          <AuditPage />
        ) : (
          <DashboardPage />
        )}
      </main>

      <footer className="bg-white border-top py-3 text-center text-muted small mt-auto">
        <div className="container">
          <span>TrustVault &copy; {new Date().getFullYear()} &middot; Cryptographically Enforced Private Document Management</span>
        </div>
      </footer>
    </div>
  );
}
