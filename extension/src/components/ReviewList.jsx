import React from 'react';

function ReviewList({ reviews, isLoading, currentRepo, onSelectReview }) {
  if (!currentRepo) {
    return (
      <section className="popup-section">
        <h2 className="section-title">📋 Recent Reviews</h2>
        <div className="reviews-list">
          <p className="reviews-empty">Navigate to a GitHub repository to see reviews.</p>
        </div>
      </section>
    );
  }

  if (isLoading) {
    return (
      <section className="popup-section">
        <h2 className="section-title">📋 Recent Reviews</h2>
        <div className="reviews-list">
          <p className="reviews-empty">Loading reviews...</p>
        </div>
      </section>
    );
  }

  const getTimeAgo = (dateStr) => {
    const date = new Date(dateStr);
    const seconds = Math.floor((new Date() - date) / 1000);
    if (seconds < 60) return 'just now';
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
    return `${Math.floor(seconds / 86400)}d ago`;
  };

  const getReviewStatusIcon = (review) => {
    if (review.status === 'completed') {
      const summary = review.summary;
      if (summary) {
        // If there are critical issues on detail, or if bugs/security are > 0, return 🚨 or ⚠️
        const hasMajorIssues = (summary.bugs || 0) > 0 || (summary.security || 0) > 0;
        const hasAnyIssues = hasMajorIssues || (summary.performance || 0) > 0 || (summary.quality || 0) > 0;
        
        if (hasMajorIssues) return '🚨';
        if (hasAnyIssues) return '⚠️';
      }
      return '✅';
    }
    if (review.status === 'failed') return '❌';
    return '⏳';
  };

  const renderReviewItem = (review) => {
    const summary = review.summary;
    const timeAgo = getTimeAgo(review.created_at);

    return (
      <div 
        key={review.id}
        className="review-item review-item--clickable"
        onClick={() => onSelectReview(review.commit_sha)}
        title="Click to view details"
      >
        <span className="review-status-icon">{getReviewStatusIcon(review)}</span>
        <div className="review-info">
          <div className="review-repo">{review.repository}</div>
          <div className="review-meta">{review.commit_sha.substring(0, 7)} · {timeAgo}</div>
        </div>
        {summary && review.status === 'completed' && (
          <div className="review-counts">
            <span className="review-count">🐞{summary.bugs || 0}</span>
            <span className="review-count">🔒{summary.security || 0}</span>
            <span className="review-count">⚡{summary.performance || 0}</span>
            <span className="review-count">✨{summary.quality || 0}</span>
          </div>
        )}
        <span className="review-arrow">›</span>
      </div>
    );
  };

  return (
    <section className="popup-section">
      <h2 className="section-title">📋 Recent Reviews</h2>
      <div className="reviews-list">
        {reviews.length === 0 ? (
          <p className="reviews-empty">No reviews yet for this repository.</p>
        ) : (
          reviews.map(renderReviewItem)
        )}
      </div>
    </section>
  );
}

export default ReviewList;
