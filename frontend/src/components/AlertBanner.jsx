import React from 'react';

export default function AlertBanner({ type = 'info', message, onClose }) {
  if (!message) return null;

  const alertClass = {
    error: 'alert-danger',
    danger: 'alert-danger',
    success: 'alert-success',
    warning: 'alert-warning',
    info: 'alert-info',
  }[type] || 'alert-info';

  const iconClass = {
    error: 'bi-exclamation-triangle-fill',
    danger: 'bi-exclamation-triangle-fill',
    success: 'bi-check-circle-fill',
    warning: 'bi-exclamation-circle-fill',
    info: 'bi-info-circle-fill',
  }[type] || 'bi-info-circle-fill';

  return (
    <div className={`alert ${alertClass} alert-dismissible fade show d-flex align-items-center mb-4 shadow-sm`} role="alert">
      <i className={`bi ${iconClass} me-2 fs-5`}></i>
      <div className="flex-grow-1">{message}</div>
      {onClose && (
        <button
          type="button"
          className="btn-close"
          aria-label="Close"
          onClick={onClose}
        ></button>
      )}
    </div>
  );
}
