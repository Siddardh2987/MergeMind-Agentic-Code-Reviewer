/**
 * MergeMind — Content Script
 *
 * Injected into GitHub pages to:
 *   • Detect the current repository and commit context
 *   • Poll the backend for review status
 *   • Inject a floating review widget (bottom-right corner)
 *   • Display loading → summary → expandable details
 *
 * This is the main UI layer that users interact with on GitHub.
 */

// ══════════════════════════════════════════════════════════════════════
// State Management
// ══════════════════════════════════════════════════════════════════════

let currentState = {
  repo: null,          // "owner/repo"
  commitSha: null,     // Current commit SHA
  reviewData: null,    // Latest review response from API
  pollTimer: null,     // Interval ID for polling
  pollAttempts: 0,     // Number of poll attempts made
  widgetVisible: false, // Whether the widget is currently shown
  widgetClosed: false,  // True when the user manually closed the widget (prevents re-show)
  lastWidgetState: null, // Last rendered state (prevents unnecessary re-renders)
};

// ══════════════════════════════════════════════════════════════════════
// GitHub Context Detection
// ══════════════════════════════════════════════════════════════════════

/**
 * Extract repository and commit context from the current GitHub URL.
 *
 * Handles URLs like:
 *   - github.com/owner/repo (repo page)
 *   - github.com/owner/repo/commit/sha (commit page)
 *   - github.com/owner/repo/pull/123 (PR page)
 *   - github.com/owner/repo/tree/branch (branch view)
 */
function detectGitHubContext() {
  const url = window.location.href;
  const pathParts = window.location.pathname.split("/").filter(Boolean);

  // Need at least owner/repo in the path
  if (pathParts.length < 2) return null;

  const owner = pathParts[0];
  const repo = pathParts[1];

  // Skip GitHub's own pages (settings, notifications, etc.)
  const githubPages = [
    "settings", "notifications", "marketplace",
    "explore", "topics", "trending", "collections",
    "sponsors", "login", "join", "new",
  ];
  if (githubPages.includes(owner)) return null;

  const context = {
    repo: `${owner}/${repo}`,
    commitSha: null,
    pageType: "repo", // repo, commit, pr, tree
  };

  // Detect specific page types
  if (pathParts.length >= 4 && pathParts[2] === "commit") {
    context.commitSha = pathParts[3];
    context.pageType = "commit";
  } else if (pathParts.length >= 4 && pathParts[2] === "pull") {
    context.pageType = "pr";
  }

  return context;
}

// ══════════════════════════════════════════════════════════════════════
// API Communication
// ══════════════════════════════════════════════════════════════════════

/**
 * Retrieve the current backend URL from storage, falling back to static config.
 */
async function getBackendUrl() {
  return new Promise((resolve) => {
    if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
      chrome.storage.local.get(["backendUrl"], (result) => {
        resolve(result.backendUrl || MERGEMIND_CONFIG.BACKEND_URL);
      });
    } else {
      resolve(MERGEMIND_CONFIG.BACKEND_URL);
    }
  });
}

/**
 * Fetch review data from the MergeMind backend.
 *
 * @param {string} commitSha - The commit SHA to look up
 * @returns {Object|null} Review data or null if not found
 */
async function fetchReview(commitSha) {
  try {
    const backendUrl = await getBackendUrl();
    const url = `${backendUrl}/review/${commitSha}`;
    const response = await fetch(url);

    if (response.status === 404) {
      return null; // No review for this commit
    }

    if (!response.ok) {
      console.error(`MergeMind: API error ${response.status}`);
      return null;
    }

    return await response.json();
  } catch (error) {
    console.error("MergeMind: Failed to fetch review:", error);
    return null;
  }
}

/**
 * Fetch the latest review for a repository.
 *
 * Used when the user is on a repo page (not a specific commit).
 *
 * @param {string} repoFullName - "owner/repo"
 * @returns {Object|null} Review data or null
 */
async function fetchLatestReview(repoFullName) {
  try {
    const backendUrl = await getBackendUrl();
    const url = `${backendUrl}/review/repo/${repoFullName}/latest`;
    const response = await fetch(url);

    if (response.status === 404) return null;
    if (!response.ok) return null;

    return await response.json();
  } catch (error) {
    console.error("MergeMind: Failed to fetch latest review:", error);
    return null;
  }
}

// ══════════════════════════════════════════════════════════════════════
// Polling Logic
// ══════════════════════════════════════════════════════════════════════

/**
 * Start polling the backend for review status.
 *
 * Polls every POLL_INTERVAL ms until:
 *   - Review status becomes 'completed' or 'failed'
 *   - MAX_POLL_ATTEMPTS is reached
 *   - The page navigates away
 */
function startPolling(commitSha) {
  stopPolling();

  currentState.pollAttempts = 0;
  currentState.commitSha = commitSha;

  showWidget("loading");
  pollOnce(commitSha);

  currentState.pollTimer = setInterval(() => {
    currentState.pollAttempts++;

    if (currentState.pollAttempts >= MERGEMIND_CONFIG.MAX_POLL_ATTEMPTS) {
      stopPolling();
      showWidget("timeout");
      return;
    }

    pollOnce(commitSha);
  }, MERGEMIND_CONFIG.POLL_INTERVAL);
}

async function pollOnce(commitSha) {
  const review = await fetchReview(commitSha);

  if (!review) {
    return;
  }

  currentState.reviewData = review;

  chrome.runtime.sendMessage({
    type: "REVIEW_STATUS_UPDATE",
    status: review.status,
    issueCount: review.summary
      ? review.summary.bugs + review.summary.security +
        review.summary.performance + review.summary.quality
      : 0,
  }).catch(() => {});

  switch (review.status) {
    case "pending":
    case "processing":
      showWidget("loading");
      break;
    case "completed":
      stopPolling();
      showWidget("completed");
      break;
    case "failed":
      stopPolling();
      showWidget("error", review.error_message);
      break;
  }
}


/**
 * Stop the polling timer.
 */
function stopPolling() {
  if (currentState.pollTimer) {
    clearInterval(currentState.pollTimer);
    currentState.pollTimer = null;
  }
}

// ══════════════════════════════════════════════════════════════════════
// Widget UI
// ══════════════════════════════════════════════════════════════════════

/**
 * Create the floating widget container if it doesn't exist.
 *
 * @returns {HTMLElement} The widget container element
 */
function getOrCreateWidget() {
  let widget = document.getElementById("mergemind-widget");

  if (!widget) {
    widget = document.createElement("div");
    widget.id = "mergemind-widget";
    widget.className = "mergemind-widget";
    document.body.appendChild(widget);
  }

  return widget;
}

/**
 * Remove the widget from the page.
 */
function removeWidget() {
  stopPolling();
  currentState.widgetVisible = false;
  currentState.widgetClosed = true;
  currentState.lastWidgetState = null;
  
  const widget = document.getElementById("mergemind-widget");
  if (widget) {
    widget.remove();
  }
}

/**
 * Show the widget in a specific state.
 *
 * @param {string} state - "loading", "completed", "error", "timeout"
 * @param {string} errorMsg - Error message (for error state)
 */
function showWidget(state, errorMsg = "") {
  // If user manually closed the widget, don't show it again
  if (currentState.widgetClosed) return;

  // Skip re-render if the widget is already showing the same state
  // This prevents polling from destroying event listeners every cycle
  if (currentState.lastWidgetState === state && currentState.widgetVisible) return;

  const widget = getOrCreateWidget();
  currentState.widgetVisible = true;
  currentState.lastWidgetState = state;

  switch (state) {
    case "loading":
      widget.innerHTML = renderLoadingState();
      break;
    case "completed":
      widget.innerHTML = renderCompletedState(currentState.reviewData);
      attachExpandHandler(widget);
      break;
    case "error":
      widget.innerHTML = renderErrorState(errorMsg);
      break;
    case "timeout":
      widget.innerHTML = renderTimeoutState();
      break;
  }

  // Attach close button handler (programmatic, not inline onclick)
  attachCloseHandler(widget);

  // Add entrance animation if not already visible
  widget.classList.remove("mergemind-exit");
  widget.classList.add("mergemind-enter");
}

// ══════════════════════════════════════════════════════════════════════
// Widget State Renderers
// ══════════════════════════════════════════════════════════════════════

/**
 * Render the loading state — shown while the review is in progress.
 */
function renderLoadingState() {
  return `
    <div class="mm-card mm-card--loading">
      <div class="mm-header">
        <div class="mm-logo">
          <span class="mm-logo-icon">🧠</span>
          <span class="mm-logo-text">MergeMind</span>
        </div>
        <button class="mm-close" title="Close">✕</button>
      </div>
      <div class="mm-body">
        <div class="mm-loader">
          <div class="mm-loader-dots">
            <span></span><span></span><span></span>
          </div>
        </div>
        <p class="mm-loading-text">🔍 Reviewing your latest commit...</p>
        <p class="mm-loading-subtext">This may take a few moments.</p>
      </div>
    </div>
  `;
}

/**
 * Render the completed state — summary + expandable details.
 */
function renderCompletedState(review) {
  if (!review || !review.summary) {
    return renderErrorState("Invalid review data received");
  }

  const { summary, issues } = review;
  const totalIssues =
    summary.bugs + summary.security + summary.performance + summary.quality;

  // Determine overall status color
  const hasIssues = totalIssues > 0;
  const hasCritical = issues?.some((i) => i.severity === "critical");
  const statusClass = hasCritical
    ? "mm-status--critical"
    : hasIssues
    ? "mm-status--warning"
    : "mm-status--clean";
  const statusEmoji = hasCritical ? "🚨" : hasIssues ? "⚠️" : "✅";
  const statusText = hasCritical
    ? "Issues Found"
    : hasIssues
    ? "Review Complete"
    : "All Clear!";

  // Build issues HTML (hidden by default)
  let issuesHtml = "";
  if (issues && issues.length > 0) {
    const issuesByCategory = groupIssues(issues);
    issuesHtml = renderIssuesList(issuesByCategory);
  }

  return `
    <div class="mm-card mm-card--completed ${statusClass}">
      <div class="mm-header">
        <div class="mm-logo">
          <span class="mm-logo-icon">🧠</span>
          <span class="mm-logo-text">MergeMind</span>
        </div>
        <button class="mm-close" title="Close">✕</button>
      </div>
      <div class="mm-body">
        <div class="mm-status">
          <span class="mm-status-emoji">${statusEmoji}</span>
          <span class="mm-status-text">${statusText}</span>
        </div>
        <div class="mm-summary">
          <div class="mm-summary-item ${summary.bugs > 0 ? "mm-has-issues" : ""}">
            <span class="mm-summary-icon">🐞</span>
            <span class="mm-summary-label">Bugs</span>
            <span class="mm-summary-count">${summary.bugs}</span>
          </div>
          <div class="mm-summary-item ${summary.security > 0 ? "mm-has-issues" : ""}">
            <span class="mm-summary-icon">🔒</span>
            <span class="mm-summary-label">Security</span>
            <span class="mm-summary-count">${summary.security}</span>
          </div>
          <div class="mm-summary-item ${summary.performance > 0 ? "mm-has-issues" : ""}">
            <span class="mm-summary-icon">⚡</span>
            <span class="mm-summary-label">Perf</span>
            <span class="mm-summary-count">${summary.performance}</span>
          </div>
          <div class="mm-summary-item ${summary.quality > 0 ? "mm-has-issues" : ""}">
            <span class="mm-summary-icon">✨</span>
            <span class="mm-summary-label">Quality</span>
            <span class="mm-summary-count">${summary.quality}</span>
          </div>
        </div>
        ${
          hasIssues
            ? `
          <button class="mm-expand-btn" id="mm-expand-btn">
            <span class="mm-expand-icon">▼</span>
            Show Details
          </button>
          <div class="mm-details" id="mm-details" style="display: none;">
            ${issuesHtml}
          </div>
        `
            : `
          <p class="mm-clean-text">No issues detected — great job! 🎉</p>
        `
        }
      </div>
      <div class="mm-footer">
        <span class="mm-commit-sha" title="${review.commit_sha}">
          ${review.commit_sha.substring(0, 7)}
        </span>
      </div>
    </div>
  `;
}

/**
 * Render the error state.
 */
function renderErrorState(errorMsg) {
  return `
    <div class="mm-card mm-card--error">
      <div class="mm-header">
        <div class="mm-logo">
          <span class="mm-logo-icon">🧠</span>
          <span class="mm-logo-text">MergeMind</span>
        </div>
        <button class="mm-close" title="Close">✕</button>
      </div>
      <div class="mm-body">
        <p class="mm-error-text">❌ Review failed</p>
        <p class="mm-error-detail">${errorMsg || "An unexpected error occurred. Please try again."}</p>
      </div>
    </div>
  `;
}

/**
 * Render the timeout state.
 */
function renderTimeoutState() {
  return `
    <div class="mm-card mm-card--timeout">
      <div class="mm-header">
        <div class="mm-logo">
          <span class="mm-logo-icon">🧠</span>
          <span class="mm-logo-text">MergeMind</span>
        </div>
        <button class="mm-close" title="Close">✕</button>
      </div>
      <div class="mm-body">
        <p class="mm-timeout-text">⏰ Review is taking longer than expected</p>
        <p class="mm-timeout-detail">The review may still complete. Refresh the page to check.</p>
      </div>
    </div>
  `;
}

// ══════════════════════════════════════════════════════════════════════
// Issue Rendering Helpers
// ══════════════════════════════════════════════════════════════════════

/**
 * Group issues by category for organized display.
 */
function groupIssues(issues) {
  const groups = {
    bug: [],
    security: [],
    performance: [],
    quality: [],
  };

  for (const issue of issues) {
    const cat = issue.category || "quality";
    if (groups[cat]) {
      groups[cat].push(issue);
    } else {
      groups.quality.push(issue);
    }
  }

  return groups;
}

/**
 * Render the expandable issues list grouped by category.
 */
function renderIssuesList(issuesByCategory) {
  const categoryConfig = {
    bug: { icon: "🐞", label: "Bugs", className: "mm-cat-bug" },
    security: { icon: "🔒", label: "Security", className: "mm-cat-security" },
    performance: { icon: "⚡", label: "Performance", className: "mm-cat-performance" },
    quality: { icon: "✨", label: "Quality", className: "mm-cat-quality" },
  };

  let html = "";

  for (const [cat, issues] of Object.entries(issuesByCategory)) {
    if (issues.length === 0) continue;

    const config = categoryConfig[cat] || categoryConfig.quality;

    html += `
      <div class="mm-category ${config.className}">
        <div class="mm-category-header">
          <span>${config.icon}</span>
          <span>${config.label}</span>
          <span class="mm-category-count">${issues.length}</span>
        </div>
        <ul class="mm-issues-list">
    `;

    for (const issue of issues) {
      const severityClass = `mm-severity-${issue.severity || "info"}`;
      html += `
        <li class="mm-issue ${severityClass}">
          <span class="mm-issue-severity">${getSeverityIcon(issue.severity)}</span>
          <div class="mm-issue-content">
            <span class="mm-issue-title">${escapeHtml(issue.title)}</span>
            <p class="mm-issue-desc">${escapeHtml(issue.description)}</p>
          </div>
        </li>
      `;
    }

    html += `</ul></div>`;
  }

  return html;
}

/**
 * Get the severity indicator icon.
 */
function getSeverityIcon(severity) {
  switch (severity) {
    case "critical":
      return "🔴";
    case "warning":
      return "🟡";
    case "info":
      return "🔵";
    default:
      return "⚪";
  }
}

/**
 * Escape HTML to prevent XSS in injected content.
 */
function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text || "";
  return div.innerHTML;
}

// ══════════════════════════════════════════════════════════════════════
// Event Handlers
// ══════════════════════════════════════════════════════════════════════

/**
 * Attach expand/collapse handler to the details button.
 */
function attachExpandHandler(widget) {
  const btn = widget.querySelector("#mm-expand-btn");
  const details = widget.querySelector("#mm-details");

  if (btn && details) {
    btn.addEventListener("click", () => {
      const isExpanded = details.style.display !== "none";

      if (isExpanded) {
        // Collapse
        details.style.display = "none";
        btn.innerHTML = '<span class="mm-expand-icon">▼</span> Show Details';
        btn.classList.remove("mm-expanded");
      } else {
        // Expand
        details.style.display = "block";
        btn.innerHTML = '<span class="mm-expand-icon">▲</span> Hide Details';
        btn.classList.add("mm-expanded");
      }
    });
  }
}

/**
 * Attach close button handler programmatically.
 *
 * Inline onclick handlers don't work in content scripts because they
 * execute in the page's main world, not the extension's isolated world.
 */
function attachCloseHandler(widget) {
  const closeBtn = widget.querySelector(".mm-close");
  if (closeBtn) {
    closeBtn.addEventListener("click", () => {
      removeWidget();
    });
  }
}

// ══════════════════════════════════════════════════════════════════════
// Initialization
// ══════════════════════════════════════════════════════════════════════

let repoPollTimer = null;

/**
 * Start periodically checking the backend for any new reviews for this repo.
 * This allows us to auto-detect git pushes while the user is looking at the page.
 */
function startRepoPolling(repoFullName) {
  stopRepoPolling();
  repoPollTimer = setInterval(async () => {
    // Only poll if we are not currently polling a pending/processing commit review
    if (currentState.pollTimer) return;

    const latestReview = await fetchLatestReview(repoFullName);
    if (latestReview) {
      // If we find a review that is newer/different from what we currently display
      const isNewCommit = latestReview.commit_sha !== currentState.commitSha;
      if (isNewCommit) {
        currentState.repo = repoFullName;
        currentState.commitSha = latestReview.commit_sha;
        currentState.reviewData = latestReview;
        // Reset manual close state so the new review is shown to the user!
        currentState.widgetClosed = false;
        currentState.lastWidgetState = null;

        if (
          latestReview.status === "pending" ||
          latestReview.status === "processing"
        ) {
          startPolling(latestReview.commit_sha);
        } else if (latestReview.status === "completed") {
          showWidget("completed");
        } else if (latestReview.status === "failed") {
          showWidget("error", latestReview.error_message);
        }
      }
    }
  }, 5000); // Check every 5 seconds for fast response
}

/**
 * Stop the repository polling timer.
 */
function stopRepoPolling() {
  if (repoPollTimer) {
    clearInterval(repoPollTimer);
    repoPollTimer = null;
  }
}

/**
 * Main initialization — runs when the content script is injected.
 * Detects GitHub context and starts polling if applicable.
 */
async function initialize() {
  const context = detectGitHubContext();
  if (!context) {
    stopRepoPolling();
    return;
  }

  currentState.repo = context.repo;

  // Start polling the repo for any new pushes/reviews
  startRepoPolling(context.repo);

  // If we're on a commit page, poll for that specific commit
  if (context.commitSha) {
    startPolling(context.commitSha);
    return;
  }

  // On repo pages, check for the latest review
  const latestReview = await fetchLatestReview(context.repo);
  if (latestReview) {
    currentState.reviewData = latestReview;
    currentState.commitSha = latestReview.commit_sha;

    if (
      latestReview.status === "pending" ||
      latestReview.status === "processing"
    ) {
      // Review is still in progress — start polling
      startPolling(latestReview.commit_sha);
    } else if (latestReview.status === "completed") {
      // Show the completed review
      showWidget("completed");
    }
  }
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "PAGE_UPDATED") {
    stopPolling();
    stopRepoPolling();
    currentState.widgetClosed = false;
    currentState.lastWidgetState = null;
    const widget = document.getElementById("mergemind-widget");
    if (widget) widget.remove();
    currentState.widgetVisible = false;
    initialize(); // Trigger instantly
  }
});

// ── Run on initial load ──────────────────────────────────────────────
initialize();
