import React, { useState } from 'react';
import { documentsApi, getErrorMessage } from '../api/client';

export default function DeleteConfirmModal({ document: doc, show, onClose, onDeleted }) {
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState(null);

  if (!show || !doc) return null;

  const handleDelete = async () => {
    setDeleting(true);
    setError(null);

    try {
      await documentsApi.delete(doc.id);
      onDeleted(doc.id);
      onClose();
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to delete document. Only the owner can delete this document.'));
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="modal fade show d-block" tabIndex="-1" style={{ backgroundColor: 'rgba(0,0,0,0.6)' }}>
      <div className="modal-dialog modal-dialog-centered">
        <div className="modal-content shadow border-0">
          <div className="modal-header bg-danger text-white">
            <h5 className="modal-title d-flex align-items-center">
              <i className="bi bi-trash-fill me-2 fs-5"></i>
              Delete Document
            </h5>
            <button
              type="button"
              className="btn-close btn-close-white"
              onClick={onClose}
              disabled={deleting}
              aria-label="Close"
            ></button>
          </div>

          <div className="modal-body p-4">
            {error && (
              <div className="alert alert-danger d-flex align-items-center py-2" role="alert">
                <i className="bi bi-exclamation-triangle-fill me-2"></i>
                <div>{error}</div>
              </div>
            )}

            <p className="mb-2">Are you sure you want to permanently delete this document?</p>
            <div className="p-3 bg-light rounded border mb-3">
              <div className="fw-bold text-dark">{doc.filename}</div>
              <small className="text-secondary">
                ID: <code>{doc.id}</code>
              </small>
            </div>
            <div className="alert alert-warning py-2 mb-0 small">
              <i className="bi bi-exclamation-circle-fill me-1"></i>
              This will remove all access for users with whom this document was shared.
            </div>
          </div>

          <div className="modal-footer bg-light border-top-0">
            <button
              type="button"
              className="btn btn-secondary"
              onClick={onClose}
              disabled={deleting}
            >
              Cancel
            </button>
            <button
              type="button"
              className="btn btn-danger d-flex align-items-center"
              onClick={handleDelete}
              disabled={deleting}
            >
              {deleting ? (
                <>
                  <span className="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
                  Deleting...
                </>
              ) : (
                <>
                  <i className="bi bi-trash me-1"></i> Yes, Delete Document
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
