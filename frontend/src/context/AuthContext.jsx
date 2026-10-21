import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { authApi } from '../api/client';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem('trustvault_token') || null);
  const [user, setUser] = useState(() => {
    try {
      const stored = localStorage.getItem('trustvault_user');
      return stored ? JSON.parse(stored) : null;
    } catch {
      return null;
    }
  });
  const [loading, setLoading] = useState(true);

  const logout = useCallback(() => {
    localStorage.removeItem('trustvault_token');
    localStorage.removeItem('trustvault_user');
    setToken(null);
    setUser(null);
  }, []);

  // Verify and refresh user info on startup if token exists
  useEffect(() => {
    async function verifySession() {
      if (!token) {
        setLoading(false);
        return;
      }
      try {
        const liveUser = await authApi.getMe();
        setUser(liveUser);
        localStorage.setItem('trustvault_user', JSON.stringify(liveUser));
      } catch (err) {
        // If token is invalid or expired, log out
        logout();
      } finally {
        setLoading(false);
      }
    }

    verifySession();
  }, [token, logout]);

  // Handle global auth expiration event triggered by 401 response interceptor
  useEffect(() => {
    const handleAuthExpired = () => {
      logout();
    };
    window.addEventListener('trustvault_auth_expired', handleAuthExpired);
    return () => {
      window.removeEventListener('trustvault_auth_expired', handleAuthExpired);
    };
  }, [logout]);

  const login = async (email, password) => {
    const data = await authApi.login({ email, password });
    const newToken = data.access_token;
    const authUser = data.user;

    localStorage.setItem('trustvault_token', newToken);
    localStorage.setItem('trustvault_user', JSON.stringify(authUser));
    setToken(newToken);
    setUser(authUser);
    return authUser;
  };

  const register = async (email, fullName, password) => {
    const newUser = await authApi.register({
      email,
      full_name: fullName,
      password,
    });
    return newUser;
  };

  const value = {
    user,
    token,
    isAuthenticated: !!token && !!user,
    isAdmin: user?.role === 'admin',
    loading,
    login,
    register,
    logout,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
