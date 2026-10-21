import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';
import { auditApi, getErrorMessage } from '../api/client';
import AlertBanner from '../components/AlertBanner';

export default function AuditPage() {
  const { isAdmin } = useAuth();
  const [events, setEvents] = useState([]);
  const [total, setTotal] = useState(0);
  const [skip, setSkip] = useState(0);
  const [limit, setLimit] = useState(25);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Filters
  const [actionFilter, setActionFilter] = useState('');
  const [outcomeFilter, setOutcomeFilter] = useState('');
  const [actorIdFilter, setActorIdFilter] = useState('');
  const [documentIdFilter, setDocumentIdFilter] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');

  const fetchAuditLogs = useCallback(async () => {
    setLoading(true);
    setError(null);

    const queryFilters = {
      skip,
      limit,
    };
    if (actionFilter) queryFilters.action = actionFilter;
    if (outcomeFilter) queryFilters.outcome = outcomeFilter;
    if (actorIdFilter.trim()) queryFilters.actor_id = actorIdFilter.trim();
    if (documentIdFilter.trim()) queryFilters.document_id = documentIdFilter.trim();
    if (startDate) queryFilters.start_date = new Date(startDate).toISOString();
    if (endDate) queryFilters.end_date = new Date(endDate).toISOString();

    try {
      const data = await auditApi.list(queryFilters);
      setEvents(data.events || []);
      setTotal(data.total || 0);
    } catch (err) {
      if (err.response?.status === 403) {
        setError('Access Denied: Administrator privileges are required to inspect the global audit trail.');
      } else {
        setError(getErrorMessage(err, 'Failed to fetch audit events.'));
      }
    } finally {
      setLoading(false);
    }
  }, [skip, limit, actionFilter, outcomeFilter, actorIdFilter, documentIdFilter, startDate, endDate]);

  useEffect(() => {
    fetchAuditLogs();
  }, [fetchAuditLogs]);

  const handleApplyFilter = (e) => {
    e.preventDefault();
    setSkip(0); // Reset to first page
    fetchAuditLogs();
  };

  const handleResetFilters = () => {
    setActionFilter('');
    setOutcomeFilter('');
    setActorIdFilter('');
    setDocumentIdFilter('');
    setStartDate('');
    setEndDate('');
    setSkip(0);
  };

  const formatTimestamp = (ts) => {
    if (!ts) return '—';
    try {
      const d = new Date(ts);
      return `${d.toLocaleDateString()} ${d.toLocaleTimeString()}`;
    } catch {
      return String(ts);
    }
  };

  const getActionBadge = (action) => {
    switch (action) {
      case 'auth.login':
        return <span className="badge bg-primary">auth.login</span>;
      case 'document.upload':
        return <span className="badge bg-success">document.upload</span>;
      case 'document.download':
        return <span className="badge bg-info text-dark">document.download</span>;
      case 'document.update':
        return <span className="badge bg-warning text-dark">document.update</span>;
      case 'document.delete':
        return <span className="badge bg-danger">document.delete</span>;
      case 'permission.grant':
        return <span className="badge bg-purple text-white" style={{ backgroundColor: '#6f42c1' }}>permission.grant</span>;
      case 'permission.revoke':
        return <span className="badge bg-secondary">permission.revoke</span>;
      default:
        return <span className="badge bg-dark">{action}</span>;
    }
  };

  const getOutcomeBadge = (outcome, statusCode) => {
    const isSuccess = outcome?.toLowerCase() === 'success';
    return (
      <span className={`badge ${isSuccess ? 'bg-success' : 'bg-danger'}`}>
        {isSuccess ? (
          <><i className="bi bi-check-circle me-1"></i>SUCCESS</>
        ) : (
          <><i className="bi bi-x-octagon me-1"></i>DENIED</>
        )}
        {statusCode && <span className="ms-1 opacity-75">({statusCode})</span>}
      </span>
    );
  };

  const currentPage = Math.floor(skip / limit) + 1;
  const totalPages = Math.max(1, Math.ceil(total / limit));

  if (!isAdmin && error && error.includes('Administrator privileges')) {
    return (
      <div className="container py-5 text-center">
        <div className="card shadow-sm border-0 rounded-4 p-5 mx-auto" style={{ maxWidth: '600px' }}>
          <i className="bi bi-shield-slash-fill text-danger fs-1 mb-3"></i>
          <h4 className="fw-bold text-dark">Administrator Access Required</h4>
          <p className="text-secondary">
            The TrustVault audit trail is restricted to users with the verified <code>admin</code> role.
            Your current user role does not have permission to view system-wide audit records.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="container-fluid px-lg-5 pb-5">
      {/* Header */}
      <div className="d-flex flex-column flex-md-row justify-content-between align-items-md-center mb-4 pb-3 border-bottom">
        <div>
          <h2 className="fw-bold text-dark mb-1 d-flex align-items-center">
            <i className="bi bi-shield-check text-primary me-2"></i>
            Security Audit Trail
          </h2>
          <p className="text-secondary small mb-0">
            Immutable inspection log recording all authentication, document operations, and authorization decisions.
          </p>
        </div>
        <div className="mt-3 mt-md-0 d-flex gap-2">
          <button
            className="btn btn-outline-secondary btn-sm d-flex align-items-center"
            onClick={fetchAuditLogs}
            disabled={loading}
          >
            <i className={`bi bi-arrow-clockwise me-1 ${loading ? 'spin-icon' : ''}`}></i>
            Refresh Logs
          </button>
        </div>
      </div>

      <AlertBanner type="error" message={error} onClose={() => setError(null)} />

      {/* Filter Form Card */}
      <div className="card shadow-sm border-0 rounded-3 mb-4 p-3 bg-white">
        <h6 className="fw-bold text-dark mb-3 d-flex align-items-center">
          <i className="bi bi-funnel-fill text-primary me-2"></i>
          Audit Filters
        </h6>
        <form onSubmit={handleApplyFilter} className="row g-2 align-items-end">
          <div className="col-12 col-sm-6 col-md-3 col-xl-2">
            <label className="form-label small fw-semibold text-secondary mb-1">Action</label>
            <select
              className="form-select form-select-sm"
              value={actionFilter}
              onChange={(e) => setActionFilter(e.target.value)}
            >
              <option value="">All Actions</option>
              <option value="auth.login">auth.login</option>
              <option value="document.upload">document.upload</option>
              <option value="document.download">document.download</option>
              <option value="document.update">document.update</option>
              <option value="document.delete">document.delete</option>
              <option value="permission.grant">permission.grant</option>
              <option value="permission.revoke">permission.revoke</option>
            </select>
          </div>

          <div className="col-12 col-sm-6 col-md-3 col-xl-2">
            <label className="form-label small fw-semibold text-secondary mb-1">Outcome</label>
            <select
              className="form-select form-select-sm"
              value={outcomeFilter}
              onChange={(e) => setOutcomeFilter(e.target.value)}
            >
              <option value="">All Outcomes</option>
              <option value="success">Success</option>
              <option value="denied">Denied</option>
            </select>
          </div>

          <div className="col-12 col-sm-6 col-md-3 col-xl-2">
            <label className="form-label small fw-semibold text-secondary mb-1">Actor User ID</label>
            <input
              type="text"
              className="form-control form-control-sm"
              placeholder="Filter by actor ID..."
              value={actorIdFilter}
              onChange={(e) => setActorIdFilter(e.target.value)}
            />
          </div>

          <div className="col-12 col-sm-6 col-md-3 col-xl-2">
            <label className="form-label small fw-semibold text-secondary mb-1">Document ID</label>
            <input
              type="text"
              className="form-control form-control-sm"
              placeholder="Filter by document ID..."
              value={documentIdFilter}
              onChange={(e) => setDocumentIdFilter(e.target.value)}
            />
          </div>

          <div className="col-12 col-sm-6 col-md-3 col-xl-2">
            <label className="form-label small fw-semibold text-secondary mb-1">From Date</label>
            <input
              type="date"
              className="form-control form-control-sm"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
            />
          </div>

          <div className="col-12 col-sm-6 col-md-3 col-xl-2">
            <label className="form-label small fw-semibold text-secondary mb-1">To Date</label>
            <input
              type="date"
              className="form-control form-control-sm"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
            />
          </div>

          <div className="col-12 mt-3 d-flex justify-content-end gap-2">
            <button
              type="button"
              className="btn btn-outline-secondary btn-sm px-3"
              onClick={handleResetFilters}
            >
              Reset Filters
            </button>
            <button
              type="submit"
              className="btn btn-primary btn-sm px-3 d-flex align-items-center"
              disabled={loading}
            >
              <i className="bi bi-search me-1"></i> Apply Filters
            </button>
          </div>
        </form>
      </div>

      {/* Audit Events Table Card */}
      <div className="card shadow-sm border-0 rounded-3 bg-white overflow-hidden">
        <div className="card-header bg-white py-3 d-flex justify-content-between align-items-center border-bottom">
          <span className="fw-semibold text-dark">
            Showing {events.length} of {total} Total Events
          </span>
          <div className="d-flex align-items-center gap-2">
            <label className="small text-secondary mb-0">Per Page:</label>
            <select
              className="form-select form-select-sm"
              style={{ width: 'auto' }}
              value={limit}
              onChange={(e) => {
                setLimit(Number(e.target.value));
                setSkip(0);
              }}
            >
              <option value="10">10</option>
              <option value="25">25</option>
              <option value="50">50</option>
              <option value="100">100</option>
            </select>
          </div>
        </div>

        {loading ? (
          <div className="text-center py-5">
            <div className="spinner-border text-primary mb-2" role="status"></div>
            <p className="text-muted small">Loading audit events...</p>
          </div>
        ) : events.length === 0 ? (
          <div className="text-center py-5 text-muted">
            <i className="bi bi-journal-x fs-1 text-secondary d-block mb-2"></i>
            <h5>No Audit Records Found</h5>
            <p className="small text-secondary">
              No audit records matched the selected filters.
            </p>
          </div>
        ) : (
          <div className="table-responsive">
            <table className="table table-hover align-middle mb-0 font-monospace-cells">
              <thead className="table-light">
                <tr className="small text-uppercase text-secondary">
                  <th>Timestamp (UTC)</th>
                  <th>Action</th>
                  <th>Outcome</th>
                  <th>Actor ID</th>
                  <th>Document ID</th>
                  <th>Reason / Details</th>
                  <th>Correlation ID</th>
                </tr>
              </thead>
              <tbody>
                {events.map((ev) => (
                  <tr key={ev.id}>
                    <td className="small text-nowrap text-dark">
                      {formatTimestamp(ev.timestamp)}
                    </td>
                    <td>{getActionBadge(ev.action)}</td>
                    <td>{getOutcomeBadge(ev.outcome, ev.status_code)}</td>
                    <td className="small text-truncate" style={{ maxWidth: '140px' }} title={ev.actor_id || 'Anonymous'}>
                      {ev.actor_id ? (
                        <code>{ev.actor_id}</code>
                      ) : (
                        <span className="text-muted fst-italic">Anonymous</span>
                      )}
                    </td>
                    <td className="small text-truncate" style={{ maxWidth: '140px' }} title={ev.document_id || '—'}>
                      {ev.document_id ? (
                        <code>{ev.document_id}</code>
                      ) : (
                        <span className="text-muted">—</span>
                      )}
                    </td>
                    <td className="small text-truncate" style={{ maxWidth: '200px' }} title={ev.reason || '—'}>
                      {ev.reason ? (
                        <span className="text-secondary">{ev.reason}</span>
                      ) : (
                        <span className="text-muted">—</span>
                      )}
                    </td>
                    <td className="small text-truncate" style={{ maxWidth: '120px' }} title={ev.correlation_id || '—'}>
                      {ev.correlation_id ? (
                        <code className="text-muted">{ev.correlation_id}</code>
                      ) : (
                        <span className="text-muted">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination Footer */}
        {total > limit && (
          <div className="card-footer bg-white d-flex justify-content-between align-items-center py-3 border-top">
            <div className="small text-secondary">
              Page <strong>{currentPage}</strong> of <strong>{totalPages}</strong>
            </div>
            <div className="btn-group">
              <button
                className="btn btn-outline-secondary btn-sm"
                onClick={() => setSkip((prev) => Math.max(0, prev - limit))}
                disabled={skip === 0 || loading}
              >
                <i className="bi bi-chevron-left me-1"></i> Previous
              </button>
              <button
                className="btn btn-outline-secondary btn-sm"
                onClick={() => setSkip((prev) => prev + limit)}
                disabled={skip + limit >= total || loading}
              >
                Next <i className="bi bi-chevron-right ms-1"></i>
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
