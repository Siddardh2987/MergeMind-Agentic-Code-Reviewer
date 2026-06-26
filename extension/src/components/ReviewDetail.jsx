import React, { useState, useEffect } from 'react';

function ReviewDetail({ commitSha, backendUrl, onBack }) {
  const [review, setReview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [expandedCategories, setExpandedCategories] = useState({});

  useEffect(() => {
    let active = true;
    async function fetchDetail() {
      setLoading(true);
      setError(null);
      try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 6000);
        const res = await fetch(`${backendUrl}/review/${commitSha}`, { signal: controller.signal });
        clearTimeout(timeoutId);
        if (res.ok) {
          const data = await res.json();
          if (active) {
            setReview(data);
          }
        } else {
          if (active) {
            let errorMsg = `Unexpected Error (${res.status})`;
            if (res.status === 400) {
              errorMsg = "Error 400: Invalid request sent to the backend.";
            } else if (res.status === 401) {
              errorMsg = "Error 401: Authentication failed.";
            } else if (res.status === 403) {
              errorMsg = "Error 403: Access denied.";
            } else if (res.status === 404) {
              errorMsg = "Error 404: No review found for this repository yet.";
            } else if (res.status === 429) {
              errorMsg = "Error 429: Rate limit exceeded. Please try again later.";
            } else if (res.status === 500) {
              errorMsg = "Error 500: Internal server error.";
            } else if (res.status === 502) {
              errorMsg = "Error 502: Upstream service unavailable.";
            } else if (res.status === 503) {
              errorMsg = "Error 503: AI model unavailable or under high demand. Please try again in a few minutes.";
            }
            setError(errorMsg);
          }
        }
      } catch (err) {
        if (active) {
          setError("Unable to connect to the MergeMind backend.");
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }
    fetchDetail();
    return () => { active = false; };
  }, [commitSha, backendUrl]);

  if (loading) {
    return (
      <section className="popup-section">
        <button className="detail-back-btn" onClick={onBack}>← Back to Reviews</button>
        <div className="detail-loading">
          <div className="detail-loader-dots">
            <span></span><span></span><span></span>
          </div>
          <p>Loading review details...</p>
        </div>
      </section>
    );
  }

  if (error || !review) {
    return (
      <section className="popup-section">
        <button className="detail-back-btn" onClick={onBack}>← Back to Reviews</button>
        <div className="detail-error">
          <p>❌ Could not load review details.</p>
          <p className="detail-error-sub">{error || 'Review not found'}</p>
        </div>
      </section>
    );
  }

  // Parse JSON data
  const summary = review.summary || (review.summary_json ? JSON.parse(review.summary_json) : { bugs: 0, security: 0, performance: 0, quality: 0 });
  const issues = review.issues || (review.issues_json ? JSON.parse(review.issues_json) : []);

  // Status mapping
  let statusEmoji = '⏳';
  let statusLabel = 'Pending';
  let statusClass = 'detail-status--pending';

  if (review.status === 'completed') {
    const total = summary.bugs + summary.security + summary.performance + summary.quality;
    const hasCritical = issues.some((i) => i.severity === 'critical');
    statusEmoji = hasCritical ? '🚨' : total > 0 ? '⚠️' : '✅';
    statusLabel = hasCritical ? 'Critical Issues' : total > 0 ? 'Issues Found' : 'All Clear!';
    statusClass = hasCritical ? 'detail-status--critical' : total > 0 ? 'detail-status--warning' : 'detail-status--clean';
  } else if (review.status === 'failed') {
    statusEmoji = '❌';
    statusLabel = 'Review Failed';
    statusClass = 'detail-status--error';
  }

  // Group issues by category
  const groupedIssues = { bug: [], security: [], performance: [], quality: [] };
  issues.forEach((issue) => {
    const cat = issue.category || 'quality';
    if (groupedIssues[cat]) {
      groupedIssues[cat].push(issue);
    } else {
      groupedIssues.quality.push(issue);
    }
  });

  const categoryConfig = {
    bug: { icon: '🐞', label: 'Bugs', className: 'detail-cat-bug' },
    security: { icon: '🔒', label: 'Security', className: 'detail-cat-security' },
    performance: { icon: '⚡', label: 'Performance', className: 'detail-cat-performance' },
    quality: { icon: '✨', label: 'Quality', className: 'detail-cat-quality' },
  };

  const getSeverityIcon = (severity) => {
    switch (severity) {
      case 'critical': return '🔴';
      case 'warning': return '🟡';
      case 'info': return '🔵';
      default: return '⚪';
    }
  };

  const toggleCategory = (cat) => {
    setExpandedCategories((prev) => ({
      ...prev,
      [cat]: !prev[cat]
    }));
  };

  return (
    <section className="popup-section">
      <button className="detail-back-btn" onClick={onBack}>← Back to Reviews</button>
      
      <div className={`detail-header ${statusClass}`}>
        <span className="detail-status-emoji">{statusEmoji}</span>
        <span className="detail-status-label">{statusLabel}</span>
      </div>

      <div className="detail-meta">
        <div className="detail-meta-row">
          <span className="detail-meta-label">Repository</span>
          <span className="detail-meta-value">{review.repository}</span>
        </div>
        <div className="detail-meta-row">
          <span className="detail-meta-label">Commit</span>
          <span className="detail-meta-value detail-mono">{review.commit_sha.substring(0, 7)}</span>
        </div>
        <div className="detail-meta-row">
          <span className="detail-meta-label">Reviewed</span>
          <span className="detail-meta-value">{new Date(review.created_at.endsWith('Z') || review.created_at.includes('+') ? review.created_at : review.created_at + 'Z').toLocaleString()}</span>
        </div>
      </div>

      {review.status === 'completed' && (
        <div className="detail-summary">
          <div className={`detail-summary-item ${summary.bugs > 0 ? 'detail-has-issues' : ''}`}>
            <span className="detail-summary-icon">🐞</span>
            <span className="detail-summary-label">Bugs</span>
            <span className="detail-summary-count">{summary.bugs}</span>
          </div>
          <div className={`detail-summary-item ${summary.security > 0 ? 'detail-has-issues' : ''}`}>
            <span className="detail-summary-icon">🔒</span>
            <span className="detail-summary-label">Security</span>
            <span className="detail-summary-count">{summary.security}</span>
          </div>
          <div className={`detail-summary-item ${summary.performance > 0 ? 'detail-has-issues' : ''}`}>
            <span className="detail-summary-icon">⚡</span>
            <span className="detail-summary-label">Perf</span>
            <span className="detail-summary-count">{summary.performance}</span>
          </div>
          <div className={`detail-summary-item ${summary.quality > 0 ? 'detail-has-issues' : ''}`}>
            <span className="detail-summary-icon">✨</span>
            <span className="detail-summary-label">Quality</span>
            <span className="detail-summary-count">{summary.quality}</span>
          </div>
        </div>
      )}

      <div className="detail-issues">
        {review.status === 'completed' && issues.length === 0 && (
          <p className="detail-clean-text">No issues detected — great job! 🎉</p>
        )}

        {review.status === 'failed' && (
          <p className="detail-error-msg">{review.error_message || 'An unexpected error occurred.'}</p>
        )}

        {review.status === 'completed' && Object.entries(groupedIssues).map(([cat, catIssues]) => {
          if (catIssues.length === 0) return null;
          const config = categoryConfig[cat];
          const isExpanded = !!expandedCategories[cat];

          return (
            <div key={cat} className={`detail-category ${config.className}`}>
              <button 
                className={`detail-category-header ${isExpanded ? 'detail-cat-expanded' : ''}`}
                onClick={() => toggleCategory(cat)}
              >
                <span className="detail-cat-info">
                  <span>{config.icon}</span>
                  <span>{config.label}</span>
                  <span className="detail-cat-count">{catIssues.length}</span>
                </span>
                <span className="detail-cat-chevron">{isExpanded ? '▲' : '▼'}</span>
              </button>
              
              {isExpanded && (
                <div className="detail-cat-body">
                  {catIssues.map((issue, idx) => (
                    <div key={idx} className={`detail-issue detail-severity-${issue.severity || 'info'}`}>
                      <span className="detail-issue-sev">{getSeverityIcon(issue.severity)}</span>
                      <div className="detail-issue-content">
                        <span className="detail-issue-title">{issue.title}</span>
                        <p className="detail-issue-desc">{issue.description}</p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}

export default ReviewDetail;
