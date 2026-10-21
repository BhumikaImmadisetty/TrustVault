import React, { useState } from 'react';
import { documentsApi, getErrorMessage } from '../api/client';

export default function DocumentCard({
  document: doc,
  currentUserId,
  onEdit,
  onShare,
  onDelete,
  onError,
}) {
  const [downloading, setDownloading] = useState(false);

  const formatFileSize = (bytes) => {
    if (!bytes && bytes !== 0) return '0 B';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  };

  const getFileIcon = (contentType, filename) => {
    const ext = filename?.split('.').pop()?.toLowerCase();
    if (contentType?.includes('pdf') || ext === 'pdf') {
      return <i className="bi bi-file-earmark-pdf-fill text-danger fs-3"></i>;
    }
    if (contentType?.includes('word') || ['doc', 'docx'].includes(ext)) {
      return <i className="bi bi-file-earmark-word-fill text-primary fs-3"></i>;
    }
    if (contentType?.includes('excel') || contentType?.includes('spreadsheet') || ['xls', 'xlsx'].includes(ext)) {
      return <i className="bi bi-file-earmark-excel-fill text-success fs-3"></i>;
    }
    if (contentType?.includes('image') || ['png', 'jpg', 'jpeg'].includes(ext)) {
      return <i className="bi bi-file-earmark-image-fill text-info fs-3"></i>;
    }
    if (contentType?.includes('text') || ext === 'txt') {
      return <i className="bi bi-file-earmark-text-fill text-secondary fs-3"></i>;
    }
    return <i className="bi bi-file-earmark-lock-fill text-dark fs-3"></i>;
  };

  const handleDownload = async () => {
    setDownloading(true);
    try {
      await documentsApi.download(doc.id, doc.filename);
    } catch (err) {
      onError?.(getErrorMessage(err, 'Failed to download document.'));
    } finally {
      setDownloading(false);
    }
  };

  const isOwner = doc.owner_id === currentUserId;

  return (
    <div className="card h-100 shadow-sm border-0 border-top border-3 border-primary rounded-3 transition-card">
      <div className="card-body d-flex flex-column p-4">
        <div className="d-flex align-items-start mb-3">
          <div className="me-3 p-2 bg-light rounded-3 d-flex align-items-center justify-content-center" style={{ width: '52px', height: '52px' }}>
            {getFileIcon(doc.content_type, doc.filename)}
          </div>
          <div className="flex-grow-1 overflow-hidden">
            <h6 className="card-title fw-bold text-dark text-truncate mb-1" title={doc.filename}>
              {doc.filename}
            </h6>
            <div className="d-flex flex-wrap gap-1 align-items-center">
              {doc.category ? (
                <span className="badge bg-secondary bg-opacity-10 text-secondary border">
                  <i className="bi bi-tag-fill me-1 small"></i>
                  {doc.category}
                </span>
              ) : (
                <span className="badge bg-light text-muted border">General</span>
              )}
              <span className="badge bg-light text-muted border">
                {formatFileSize(doc.size_bytes)}
              </span>
              {isOwner ? (
                <span className="badge bg-primary bg-opacity-10 text-primary border border-primary border-opacity-25">
                  Owner
                </span>
              ) : (
                <span className="badge bg-info bg-opacity-10 text-info border border-info border-opacity-25">
                  Shared
                </span>
              )}
            </div>
          </div>
        </div>

        {doc.description ? (
          <p className="card-text text-secondary small flex-grow-1 text-truncate-2 mb-3">
            {doc.description}
          </p>
        ) : (
          <p className="card-text text-muted small fst-italic flex-grow-1 mb-3">
            No description provided.
          </p>
        )}

        <div className="text-muted small border-top pt-2 mb-3" style={{ fontSize: '0.8rem' }}>
          <div className="d-flex justify-content-between mb-1">
            <span>Uploaded:</span>
            <span>{doc.created_at ? new Date(doc.created_at).toLocaleDateString() : '—'}</span>
          </div>
          {doc.updated_at && doc.updated_at !== doc.created_at && (
            <div className="d-flex justify-content-between">
              <span>Updated:</span>
              <span>{new Date(doc.updated_at).toLocaleDateString()}</span>
            </div>
          )}
        </div>

        <div className="d-flex flex-wrap gap-2 mt-auto">
          <button
            className="btn btn-primary btn-sm flex-grow-1 d-flex align-items-center justify-content-center"
            onClick={handleDownload}
            disabled={downloading}
            title="Download document"
          >
            {downloading ? (
              <>
                <span className="spinner-border spinner-border-sm me-1" role="status"></span>
                Downloading...
              </>
            ) : (
              <>
                <i className="bi bi-download me-1"></i> Download
              </>
            )}
          </button>

          <button
            className="btn btn-outline-secondary btn-sm"
            onClick={() => onEdit(doc)}
            title="Edit metadata"
          >
            <i className="bi bi-pencil"></i>
          </button>

          <button
            className="btn btn-outline-secondary btn-sm"
            onClick={() => onShare(doc)}
            title="Manage sharing & permissions"
          >
            <i className="bi bi-share"></i>
          </button>

          <button
            className="btn btn-outline-danger btn-sm"
            onClick={() => onDelete(doc)}
            title="Delete document"
          >
            <i className="bi bi-trash"></i>
          </button>
        </div>
      </div>
    </div>
  );
}
