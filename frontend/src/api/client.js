import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Accept': 'application/json',
  },
});

// Attach Authorization Bearer token to all outgoing requests
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('trustvault_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Intercept 401 Unauthorized responses to safely handle session expiration
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.status === 401) {
      // Clear expired credentials
      localStorage.removeItem('trustvault_token');
      localStorage.removeItem('trustvault_user');
      window.dispatchEvent(new Event('trustvault_auth_expired'));
    }
    return Promise.reject(error);
  }
);

// Helper to extract clean, safe error messages from API responses
export function getErrorMessage(error, defaultMessage = 'An unexpected error occurred.') {
  if (!error) return defaultMessage;
  if (error.response && error.response.data) {
    const detail = error.response.data.detail;
    if (typeof detail === 'string') {
      return detail;
    }
    if (Array.isArray(detail) && detail.length > 0) {
      // FastAPI validation error array
      return detail.map((err) => `${err.loc?.slice(-1)[0] || 'Field'}: ${err.msg}`).join(', ');
    }
    if (error.response.data.message) {
      return error.response.data.message;
    }
  }
  if (error.message) {
    if (error.message.includes('Network Error')) {
      return 'Unable to reach the TrustVault backend server. Please ensure the backend is running.';
    }
    return error.message;
  }
  return defaultMessage;
}

// ---------------------------------------------------------------------------
// Authentication API
// ---------------------------------------------------------------------------
export const authApi = {
  login: async (credentials) => {
    const response = await apiClient.post('/auth/login', credentials);
    return response.data;
  },
  register: async (userData) => {
    const response = await apiClient.post('/auth/register', userData);
    return response.data;
  },
  getMe: async () => {
    const response = await apiClient.get('/auth/me');
    return response.data;
  },
};

// ---------------------------------------------------------------------------
// Document Management API
// ---------------------------------------------------------------------------
export const documentsApi = {
  list: async (skip = 0, limit = 50) => {
    const response = await apiClient.get('/documents/', {
      params: { skip, limit },
    });
    return response.data;
  },
  upload: async (file, description = '', category = '') => {
    const formData = new FormData();
    formData.append('file', file);

    const params = {};
    if (description && description.trim()) {
      params.description = description.trim();
    }
    if (category && category.trim()) {
      params.category = category.trim();
    }

    const response = await apiClient.post('/documents/upload', formData, {
      params,
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },
  download: async (documentId, fallbackFilename = 'document') => {
    const response = await apiClient.get(`/documents/${documentId}/download`, {
      responseType: 'blob',
    });

    // Extract filename from Content-Disposition header if available
    let filename = fallbackFilename;
    const disposition = response.headers['content-disposition'];
    if (disposition && disposition.includes('filename=')) {
      const match = disposition.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i);
      if (match && match[1]) {
        filename = decodeURIComponent(match[1]);
      }
    }

    // Trigger browser download safely
    const blob = new Blob([response.data], {
      type: response.headers['content-type'] || 'application/octet-stream',
    });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
  },
  update: async (documentId, updateData) => {
    const response = await apiClient.patch(`/documents/${documentId}`, updateData);
    return response.data;
  },
  delete: async (documentId) => {
    const response = await apiClient.delete(`/documents/${documentId}`);
    return response.data;
  },
  listPermissions: async (documentId) => {
    const response = await apiClient.get(`/documents/${documentId}/permissions`);
    return response.data;
  },
  grantPermission: async (documentId, grantData) => {
    const response = await apiClient.post(`/documents/${documentId}/permissions`, grantData);
    return response.data;
  },
  revokePermission: async (documentId, granteeId) => {
    const response = await apiClient.delete(`/documents/${documentId}/permissions/${granteeId}`);
    return response.data;
  },
};

// ---------------------------------------------------------------------------
// Audit Trail API (Admin Only)
// ---------------------------------------------------------------------------
export const auditApi = {
  list: async (filters = {}) => {
    const cleanedParams = {};
    Object.entries(filters).forEach(([key, val]) => {
      if (val !== undefined && val !== null && String(val).trim() !== '') {
        cleanedParams[key] = val;
      }
    });

    const response = await apiClient.get('/audit/', {
      params: cleanedParams,
    });
    return response.data;
  },
};
