import React, { useState, useEffect } from 'react';
import { documentsApi, getErrorMessage } from '../api/client';

export default function DocumentEditModal({ document: doc, show, onClose, onUpdated }) {
  const [filename, setFilename] = useState('');
  const [description, setDescription] = useState('');
  const [category, setCategory] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (doc) {
      setFilename(doc.filename || '');
      setDescription(doc.description || '');
      setCategory(doc.category || '');
      setError(null);
    }
  }, [doc]);

  if (!show || !doc) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);

    const updatePayload = {};
    if (filename.trim()) updatePayload.filename = filename.trim();
    updatePayload.description = description.trim();
    updatePayload.category = category.trim();

    try {
      const updatedDoc = await documentsApi.update(doc.id, updatePayload);
      onUpdated(updatedDoc);
      onClose();
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to update document metadata.'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="modal fade show d-block" tabIndex="-1" style={{ backgroundColor: 'rgba(0,0,0,0.6)' }}>
      <div className="modal-dialog modal-dialog-centered">
        <div className="modal-content shadow border-0">
          <div className="modal-header bg-dark text-white">
            <h5 className="modal-title d-flex align-items-center">
              <i className="bi bi-pencil-square me-2 fs-5"></i>
              Update Document Metadata
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
                <label className="form-label fw-semibold">Filename *</label>
                <input
                  type="text"
                  className="form-control"
                  value={filename}
                  onChange={(e) => setFilename(e.target.value)}
                  required
                  disabled={submitting}
                />
              </div>

              <div className="mb-3">
                <label className="form-label fw-semibold">Category</label>
                <input
                  type="text"
                  className="form-control"
                  placeholder="e.g. Finance, Legal"
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  maxLength={100}
                  disabled={submitting}
                />
              </div>

              <div className="mb-3">
                <label className="form-label fw-semibold">Description</label>
                <textarea
                  className="form-control"
                  rows="3"
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
                disabled={submitting || !filename.trim()}
              >
                {submitting ? (
                  <>
                    <span className="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
                    Saving...
                  </>
                ) : (
                  <>
                    <i className="bi bi-check2-circle me-1"></i> Save Changes
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
