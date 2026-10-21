import React, { useState, useEffect } from 'react';
import { documentsApi, getErrorMessage } from '../api/client';

export default function PermissionModal({ document: doc, show, onClose }) {
  const [permissions, setPermissions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [granteeEmail, setGranteeEmail] = useState('');
  const [permissionLevel, setPermissionLevel] = useState('read');
  const [granting, setGranting] = useState(false);
  const [revokingId, setRevokingId] = useState(null);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  const fetchPermissions = async () => {
    if (!doc) return;
    setLoading(true);
    setError(null);
    try {
      const data = await documentsApi.listPermissions(doc.id);
      setPermissions(data.permissions || []);
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load permissions. Only the document owner can view permissions.'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (show && doc) {
      setError(null);
      setSuccess(null);
      setGranteeEmail('');
      setPermissionLevel('read');
      fetchPermissions();
    }
  }, [show, doc]);

  if (!show || !doc) return null;

  const handleGrant = async (e) => {
    e.preventDefault();
    if (!granteeEmail.trim()) {
      setError('Please provide a recipient email or user ID.');
      return;
    }

    setGranting(true);
    setError(null);
    setSuccess(null);

    try {
      const grantPayload = {
        grantee_email: granteeEmail.trim().includes('@') ? granteeEmail.trim() : undefined,
        grantee_id: !granteeEmail.trim().includes('@') ? granteeEmail.trim() : undefined,
        permission_level: permissionLevel,
      };

      await documentsApi.grantPermission(doc.id, grantPayload);
      setSuccess(`Permission successfully granted to ${granteeEmail.trim()}.`);
      setGranteeEmail('');
      await fetchPermissions();
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to grant permission.'));
    } finally {
      setGranting(false);
    }
  };

  const handleRevoke = async (granteeId, granteeIdentifier) => {
    setRevokingId(granteeId);
    setError(null);
    setSuccess(null);

    try {
      await documentsApi.revokePermission(doc.id, granteeId);
      setSuccess(`Permission immediately revoked for ${granteeIdentifier || granteeId}.`);
      await fetchPermissions();
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to revoke permission.'));
    } finally {
      setRevokingId(null);
    }
  };

  return (
    <div className="modal fade show d-block" tabIndex="-1" style={{ backgroundColor: 'rgba(0,0,0,0.6)' }}>
      <div className="modal-dialog modal-dialog-centered modal-lg">
        <div className="modal-content shadow border-0">
          <div className="modal-header bg-dark text-white">
            <h5 className="modal-title d-flex align-items-center">
              <i className="bi bi-shield-shaded text-primary me-2 fs-5"></i>
              Manage Access: <span className="text-light ms-2 text-truncate" style={{ maxWidth: '400px' }}>{doc.filename}</span>
            </h5>
            <button
              type="button"
              className="btn-close btn-close-white"
              onClick={onClose}
              disabled={granting || !!revokingId}
              aria-label="Close"
            ></button>
          </div>

          <div className="modal-body p-4">
            {error && (
              <div className="alert alert-danger d-flex align-items-center py-2" role="alert">
                <i className="bi bi-exclamation-triangle-fill me-2"></i>
                <div className="flex-grow-1">{error}</div>
                <button type="button" className="btn-close" onClick={() => setError(null)}></button>
              </div>
            )}

            {success && (
              <div className="alert alert-success d-flex align-items-center py-2" role="alert">
                <i className="bi bi-check-circle-fill me-2"></i>
                <div className="flex-grow-1">{success}</div>
                <button type="button" className="btn-close" onClick={() => setSuccess(null)}></button>
              </div>
            )}

            {/* Grant Permission Form */}
            <div className="card border-0 bg-light p-3 mb-4 rounded shadow-sm">
              <h6 className="fw-bold mb-3 d-flex align-items-center text-dark">
                <i className="bi bi-person-plus-fill text-primary me-2"></i>
                Grant Document Access
              </h6>
              <form onSubmit={handleGrant} className="row g-2 align-items-center">
                <div className="col-md-6">
                  <input
                    type="text"
                    className="form-control"
                    placeholder="Recipient email or User ID"
                    value={granteeEmail}
                    onChange={(e) => setGranteeEmail(e.target.value)}
                    disabled={granting}
                    required
                  />
                </div>
                <div className="col-md-3">
                  <select
                    className="form-select"
                    value={permissionLevel}
                    onChange={(e) => setPermissionLevel(e.target.value)}
                    disabled={granting}
                  >
                    <option value="read">Read Only (Download)</option>
                    <option value="edit">Edit (Metadata & Download)</option>
                  </select>
                </div>
                <div className="col-md-3">
                  <button
                    type="submit"
                    className="btn btn-primary w-100 d-flex align-items-center justify-content-center"
                    disabled={granting || !granteeEmail.trim()}
                  >
                    {granting ? (
                      <>
                        <span className="spinner-border spinner-border-sm me-2" role="status"></span>
                        Granting...
                      </>
                    ) : (
                      <>
                        <i className="bi bi-check2 me-1"></i> Grant Access
                      </>
                    )}
                  </button>
                </div>
              </form>
              <div className="form-text mt-2 small text-muted">
                <i className="bi bi-info-circle me-1"></i>
                Access grants take immediate effect and are recorded in the immutable audit trail.
              </div>
            </div>

            {/* Active Permissions List */}
            <h6 className="fw-bold mb-3 text-dark d-flex align-items-center">
              <i className="bi bi-people-fill text-secondary me-2"></i>
              Active Access Grants ({permissions.length})
            </h6>

            {loading ? (
              <div className="text-center py-4 text-secondary">
                <div className="spinner-border spinner-border-sm me-2" role="status"></div>
                Checking active permissions...
              </div>
            ) : permissions.length === 0 ? (
              <div className="text-center py-4 text-muted bg-light rounded border border-dashed">
                <i className="bi bi-lock-fill fs-3 text-secondary d-block mb-1"></i>
                Private to owner. No external users have access to this document.
              </div>
            ) : (
              <div className="table-responsive">
                <table className="table table-hover align-middle mb-0">
                  <thead className="table-light">
                    <tr>
                      <th>Recipient</th>
                      <th>Level</th>
                      <th>Granted Date</th>
                      <th className="text-end">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {permissions.map((perm) => (
                      <tr key={perm.id}>
                        <td>
                          <div className="fw-semibold text-dark">
                            {perm.grantee_email || 'Registered User'}
                          </div>
                          <small className="text-secondary font-monospace">
                            ID: {perm.grantee_id}
                          </small>
                        </td>
                        <td>
                          <span
                            className={`badge ${
                              perm.permission_level === 'edit'
                                ? 'bg-warning text-dark'
                                : 'bg-info text-dark'
                            }`}
                          >
                            {perm.permission_level?.toUpperCase()}
                          </span>
                        </td>
                        <td className="small text-secondary">
                          {perm.created_at
                            ? new Date(perm.created_at).toLocaleString()
                            : '—'}
                        </td>
                        <td className="text-end">
                          <button
                            type="button"
                            className="btn btn-outline-danger btn-sm"
                            onClick={() =>
                              handleRevoke(
                                perm.grantee_id,
                                perm.grantee_email || perm.grantee_id
                              )
                            }
                            disabled={revokingId === perm.grantee_id}
                            title="Immediately revoke access"
                          >
                            {revokingId === perm.grantee_id ? (
                              <span className="spinner-border spinner-border-sm"></span>
                            ) : (
                              <>
                                <i className="bi bi-x-circle me-1"></i> Revoke
                              </>
                            )}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div className="modal-footer bg-light border-top-0">
            <button
              type="button"
              className="btn btn-secondary"
              onClick={onClose}
              disabled={granting || !!revokingId}
            >
              Done
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
