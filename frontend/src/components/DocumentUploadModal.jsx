import React, { useState } from 'react';
import { documentsApi, getErrorMessage } from '../api/client';

export default function DocumentUploadModal({ show, onClose, onUploaded }) {
  const [file, setFile] = useState(null);
  const [description, setDescription] = useState('');
  const [category, setCategory] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  if (!show) return null;

  const handleFileChange = (e) => {
    setError(null);
    const selected = e.target.files[0];
    if (!selected) {
      setFile(null);
      return;
    }

    // Client-side quick check: 10 MB limit
    if (selected.size > 10 * 1024 * 1024) {
      setError('Selected file exceeds the maximum allowed size of 10 MB.');
      setFile(null);
      e.target.value = '';
      return;
    }

    setFile(selected);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!file) {
      setError('Please select a file to upload.');
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      const newDoc = await documentsApi.upload(file, description, category);
      setFile(null);
      setDescription('');
      setCategory('');
      onUploaded(newDoc);
      onClose();
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to upload document.'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="modal fade show d-block" tabIndex="-1" style={{ backgroundColor: 'rgba(0,0,0,0.6)' }}>
      <div className="modal-dialog modal-dialog-centered">
        <div className="modal-content shadow border-0">
          <div className="modal-header bg-primary text-white">
            <h5 className="modal-title d-flex align-items-center">
              <i className="bi bi-cloud-arrow-up-fill me-2 fs-5"></i>
              Upload Secure Document
            </h5>
            <button
              type="button"
              className="btn-close btn-close-white"
              onClick={onClose}
              disabled={submitting}
              aria-label="Close"
            ></button>
          </div>

          <form onSubmit={handleSubmit}>
            <div className="modal-body p-4">
              {error && (
                <div className="alert alert-danger d-flex align-items-center py-2" role="alert">
                  <i className="bi bi-exclamation-triangle-fill me-2"></i>
                  <div>{error}</div>
                </div>
              )}

              <div className="mb-3">
                <label className="form-label fw-semibold">Select File *</label>
                <input
                  type="file"
                  className="form-control"
                  onChange={handleFileChange}
                  disabled={submitting}
                  required
                />
                <div className="form-text">
                  Permitted formats: PDF, DOC/DOCX, XLS/XLSX, TXT, JPEG, PNG (Max 10 MB).
                </div>
              </div>

              <div className="mb-3">
                <label className="form-label fw-semibold">Category (Optional)</label>
                <input
                  type="text"
                  className="form-control"
                  placeholder="e.g. Legal, Finance, Identity, Contracts"
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  maxLength={100}
                  disabled={submitting}
                />
              </div>

              <div className="mb-3">
                <label className="form-label fw-semibold">Description (Optional)</label>
                <textarea
                  className="form-control"
                  rows="3"
                  placeholder="Provide context or notes about this document..."
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  maxLength={500}
                  disabled={submitting}
                ></textarea>
              </div>
            </div>

            <div className="modal-footer bg-light border-top-0">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={onClose}
                disabled={submitting}
              >
                Cancel
              </button>
              <button
                type="submit"
                className="btn btn-primary d-flex align-items-center"
                disabled={submitting || !file}
              >
                {submitting ? (
                  <>
                    <span className="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
                    Uploading Securely...
                  </>
                ) : (
                  <>
                    <i className="bi bi-shield-check me-2"></i>
                    Upload to Vault
                  </>
                )}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
