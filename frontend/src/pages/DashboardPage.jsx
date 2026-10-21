import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';
import { documentsApi, getErrorMessage } from '../api/client';
import DocumentCard from '../components/DocumentCard';
import DocumentUploadModal from '../components/DocumentUploadModal';
import DocumentEditModal from '../components/DocumentEditModal';
import DeleteConfirmModal from '../components/DeleteConfirmModal';
import PermissionModal from '../components/PermissionModal';
import AlertBanner from '../components/AlertBanner';

export default function DashboardPage() {
  const { user } = useAuth();
  const [documents, setDocuments] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  // Filter & Search states
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('all');

  // Modals state
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [editingDoc, setEditingDoc] = useState(null);
  const [sharingDoc, setSharingDoc] = useState(null);
  const [deletingDoc, setDeletingDoc] = useState(null);

  const fetchDocuments = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await documentsApi.list(0, 100);
      setDocuments(data.documents || []);
      setTotal(data.total || 0);
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to retrieve documents from the vault.'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  // Extract unique categories for filter dropdown
  const categories = useMemo(() => {
    const cats = new Set();
    documents.forEach((d) => {
      if (d.category && d.category.trim()) {
        cats.add(d.category.trim());
      }
    });
    return Array.from(cats).sort();
  }, [documents]);

  // Filtered documents
  const filteredDocuments = useMemo(() => {
    return documents.filter((doc) => {
      const matchesSearch =
        searchQuery === '' ||
        doc.filename?.toLowerCase().includes(searchQuery.toLowerCase()) ||
        doc.description?.toLowerCase().includes(searchQuery.toLowerCase());

      const matchesCategory =
        selectedCategory === 'all' ||
        (doc.category && doc.category.toLowerCase() === selectedCategory.toLowerCase());

      return matchesSearch && matchesCategory;
    });
  }, [documents, searchQuery, selectedCategory]);

  const handleDocumentUploaded = (newDoc) => {
    setSuccess(`Document "${newDoc.filename}" uploaded successfully to your vault.`);
    fetchDocuments();
  };

  const handleDocumentUpdated = (updatedDoc) => {
    setSuccess(`Metadata for "${updatedDoc.filename}" updated successfully.`);
    fetchDocuments();
  };

  const handleDocumentDeleted = (deletedId) => {
    setSuccess('Document deleted successfully and removed from storage.');
    setDocuments((prev) => prev.filter((d) => d.id !== deletedId));
    setTotal((prev) => Math.max(0, prev - 1));
  };

  return (
    <div className="container-fluid px-lg-5 pb-5">
      {/* Top Banner / Hero */}
      <div className="d-flex flex-column flex-md-row justify-content-between align-items-md-center mb-4 pb-3 border-bottom">
        <div>
          <h2 className="fw-bold text-dark mb-1 d-flex align-items-center">
            <i className="bi bi-folder2 text-primary me-2"></i>
            Vault Documents
          </h2>
          <p className="text-secondary small mb-0">
            Secure, access-controlled documents with cryptographic storage and permission enforcement.
          </p>
        </div>
        <div className="mt-3 mt-md-0">
          <button
            className="btn btn-primary px-3 py-2 shadow-sm d-flex align-items-center"
            onClick={() => setShowUploadModal(true)}
          >
            <i className="bi bi-cloud-arrow-up-fill me-2 fs-5"></i>
            Upload Document
          </button>
        </div>
      </div>

      <AlertBanner type="error" message={error} onClose={() => setError(null)} />
      <AlertBanner type="success" message={success} onClose={() => setSuccess(null)} />

      {/* Summary Stat Cards */}
      <div className="row g-3 mb-4">
        <div className="col-12 col-sm-6 col-xl-3">
          <div className="card shadow-sm border-0 rounded-3 p-3 bg-white">
            <div className="d-flex align-items-center">
              <div className="p-3 bg-primary bg-opacity-10 text-primary rounded-3 me-3">
                <i className="bi bi-files fs-3"></i>
              </div>
              <div>
                <small className="text-secondary fw-semibold">Total Documents</small>
                <h4 className="fw-bold mb-0 text-dark">{total}</h4>
              </div>
            </div>
          </div>
        </div>

        <div className="col-12 col-sm-6 col-xl-3">
          <div className="card shadow-sm border-0 rounded-3 p-3 bg-white">
            <div className="d-flex align-items-center">
              <div className="p-3 bg-success bg-opacity-10 text-success rounded-3 me-3">
                <i className="bi bi-tags fs-3"></i>
              </div>
              <div>
                <small className="text-secondary fw-semibold">Categories</small>
                <h4 className="fw-bold mb-0 text-dark">{categories.length}</h4>
              </div>
            </div>
          </div>
        </div>

        <div className="col-12 col-sm-6 col-xl-3">
          <div className="card shadow-sm border-0 rounded-3 p-3 bg-white">
            <div className="d-flex align-items-center">
              <div className="p-3 bg-info bg-opacity-10 text-info rounded-3 me-3">
                <i className="bi bi-shield-check fs-3"></i>
              </div>
              <div>
                <small className="text-secondary fw-semibold">Storage Mode</small>
                <h5 className="fw-bold mb-0 text-dark">Private Vault</h5>
              </div>
            </div>
          </div>
        </div>

        <div className="col-12 col-sm-6 col-xl-3">
          <div className="card shadow-sm border-0 rounded-3 p-3 bg-white">
            <div className="d-flex align-items-center">
              <div className="p-3 bg-warning bg-opacity-10 text-warning rounded-3 me-3">
                <i className="bi bi-clock-history fs-3"></i>
              </div>
              <div>
                <small className="text-secondary fw-semibold">Audit Logging</small>
                <h5 className="fw-bold mb-0 text-dark">Active</h5>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="card shadow-sm border-0 rounded-3 mb-4 p-3 bg-white">
        <div className="row g-2 align-items-center">
          <div className="col-12 col-md-6 col-lg-7">
            <div className="input-group">
              <span className="input-group-text bg-light border-end-0 text-muted">
                <i className="bi bi-search"></i>
              </span>
              <input
                type="text"
                className="form-control border-start-0"
                placeholder="Search documents by filename or description..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
              {searchQuery && (
                <button
                  className="btn btn-outline-secondary border-start-0 bg-light"
                  type="button"
                  onClick={() => setSearchQuery('')}
                >
                  <i className="bi bi-x-lg"></i>
                </button>
              )}
            </div>
          </div>

          <div className="col-12 col-sm-6 col-md-3 col-lg-3">
            <select
              className="form-select"
              value={selectedCategory}
              onChange={(e) => setSelectedCategory(e.target.value)}
            >
              <option value="all">All Categories ({documents.length})</option>
              {categories.map((cat) => (
                <option key={cat} value={cat}>
                  {cat}
                </option>
              ))}
            </select>
          </div>

          <div className="col-12 col-sm-6 col-md-3 col-lg-2 text-end">
            <button
              className="btn btn-outline-secondary w-100 d-flex align-items-center justify-content-center"
              onClick={fetchDocuments}
              disabled={loading}
              title="Refresh documents list"
            >
              <i className={`bi bi-arrow-clockwise me-1 ${loading ? 'spin-icon' : ''}`}></i>
              Refresh
            </button>
          </div>
        </div>
      </div>

      {/* Documents Grid or States */}
      {loading ? (
        <div className="text-center py-5">
          <div className="spinner-border text-primary mb-3" role="status" style={{ width: '3rem', height: '3rem' }}>
            <span className="visually-hidden">Loading...</span>
          </div>
          <p className="text-muted">Loading documents from your secure vault...</p>
        </div>
      ) : filteredDocuments.length === 0 ? (
        <div className="card border-0 shadow-sm p-5 text-center bg-white rounded-3 my-4">
          <div className="mb-3">
            <i className="bi bi-folder-x text-muted" style={{ fontSize: '4rem' }}></i>
          </div>
          <h4 className="fw-bold text-dark">No Documents Found</h4>
          <p className="text-secondary mx-auto" style={{ maxWidth: '500px' }}>
            {searchQuery || selectedCategory !== 'all'
              ? 'No documents matched your search query or category filter. Try clearing your filters.'
              : 'Your TrustVault is currently empty. Upload your first private document to get started.'}
          </p>
          {(searchQuery || selectedCategory !== 'all') ? (
            <div>
              <button
                className="btn btn-outline-secondary btn-sm"
                onClick={() => {
                  setSearchQuery('');
                  setSelectedCategory('all');
                }}
              >
                Clear Filters
              </button>
            </div>
          ) : (
            <div>
              <button className="btn btn-primary" onClick={() => setShowUploadModal(true)}>
                <i className="bi bi-cloud-arrow-up-fill me-2"></i>
                Upload First Document
              </button>
            </div>
          )}
        </div>
      ) : (
        <div className="row g-4">
          {filteredDocuments.map((doc) => (
            <div key={doc.id} className="col-12 col-md-6 col-lg-4 col-xl-3">
              <DocumentCard
                document={doc}
                currentUserId={user?.id}
                onEdit={(d) => setEditingDoc(d)}
                onShare={(d) => setSharingDoc(d)}
                onDelete={(d) => setDeletingDoc(d)}
                onError={(msg) => setError(msg)}
              />
            </div>
          ))}
        </div>
      )}

      {/* Modals */}
      <DocumentUploadModal
        show={showUploadModal}
        onClose={() => setShowUploadModal(false)}
        onUploaded={handleDocumentUploaded}
      />

      <DocumentEditModal
        document={editingDoc}
        show={!!editingDoc}
        onClose={() => setEditingDoc(null)}
        onUpdated={handleDocumentUpdated}
      />

      <DeleteConfirmModal
        document={deletingDoc}
        show={!!deletingDoc}
        onClose={() => setDeletingDoc(null)}
        onDeleted={handleDocumentDeleted}
      />

      <PermissionModal
        document={sharingDoc}
        show={!!sharingDoc}
        onClose={() => setSharingDoc(null)}
      />
    </div>
  );
}
