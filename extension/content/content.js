/**
 * MergeMind — Content Script
 *
 * Injected into GitHub pages to:
 *   • Detect the current repository and commit context
 *   • Open WebSocket connections to receive real-time review updates
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
  widgetVisible: false, // Whether the widget is currently shown
  widgetClosed: false,  // True when the user manually closed the widget (prevents re-show)
  lastWidgetState: null, // Last rendered state (prevents unnecessary re-renders)
};

// Active WebSocket connections
let commitWs = null;      // WebSocket for commit-level updates
let repoWs = null;        // WebSocket for repo-level updates
let commitWsRetries = 0;  // Reconnect attempt counter for commit WS
let repoWsRetries = 0;    // Reconnect attempt counter for repo WS
let commitWsTimer = null;  // Reconnect timer for commit WS
let repoWsTimer = null;    // Reconnect timer for repo WS

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
// API Communication (kept for initial fetches / popup support)
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
 * Convert an HTTP(S) URL to its WebSocket equivalent.
 *   http://localhost:8000  → ws://localhost:8000
 *   https://api.example.com → wss://api.example.com
 */
function toWsUrl(httpUrl) {
  return httpUrl.replace(/^http/, "ws");
}

/**
 * Fetch review data from the MergeMind backend (HTTP).
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
 * Fetch the latest review for a repository (HTTP).
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
// WebSocket Connections (replaces polling)
// ══════════════════════════════════════════════════════════════════════

/**
 * Open a WebSocket connection to receive real-time updates
 * for a specific commit's review.
 *
 * The server sends the current review state immediately on connect,
 * then pushes updates whenever the status changes.
 *
 * @param {string} commitSha - The commit SHA to subscribe to
 */
async function connectCommitWebSocket(commitSha) {
  disconnectCommitWebSocket();

  currentState.commitSha = commitSha;
  commitWsRetries = 0;

  showWidget("loading");
  await _openCommitWs(commitSha);
}

async function _openCommitWs(commitSha) {
  const backendUrl = await getBackendUrl();
  const wsUrl = `${toWsUrl(backendUrl)}/ws/review/${commitSha}`;

  try {
    commitWs = new WebSocket(wsUrl);
  } catch (e) {
    console.error("MergeMind: Failed to create commit WebSocket:", e);
    _scheduleCommitReconnect(commitSha);
    return;
  }

  commitWs.onopen = () => {
    console.log(`MergeMind: Commit WS connected for ${commitSha.substring(0, 8)}`);
    commitWsRetries = 0; // Reset retries on successful connect
  };

  commitWs.onmessage = (event) => {
    if (event.data === "pong") return; // Keep-alive response

    try {
      const review = JSON.parse(event.data);
      _handleCommitUpdate(review);
    } catch (e) {
      console.error("MergeMind: Failed to parse WS message:", e);
    }
  };

  commitWs.onclose = (event) => {
    console.log(`MergeMind: Commit WS closed (code: ${event.code})`);
    commitWs = null;
    // Only reconnect if we haven't already received a terminal state
    if (!_isTerminalState(currentState.reviewData)) {
      _scheduleCommitReconnect(commitSha);
    }
  };

  commitWs.onerror = (error) => {
    console.error("MergeMind: Commit WS error:", error);
    // onclose will fire after onerror, which handles reconnection
  };
}

/**
 * Handle an incoming review status update from the commit WebSocket.
 */
async function _handleCommitUpdate(review) {
  if (review.status === "not_found") {
    // No review exists yet — trigger one automatically!
    try {
      const backendUrl = await getBackendUrl();
      const response = await fetch(`${backendUrl}/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          commit_sha: currentState.commitSha,
          repository: currentState.repo,
          github_username: currentState.repo.split("/")[0] || "unknown"
        })
      });
      if (!response.ok) {
        console.error("MergeMind: Failed to trigger review:", response.statusText);
        showWidget("error", "Failed to trigger review on backend");
      }
    } catch (err) {
      console.error("MergeMind: Failed to trigger review:", err);
      showWidget("error", "Connection error trying to trigger review");
    }
    return;
  }

  currentState.reviewData = review;

  // Notify the background script for badge updates
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
      disconnectCommitWebSocket(); // No more updates needed
      showWidget("completed");
      break;
    case "failed":
      disconnectCommitWebSocket(); // No more updates needed
      showWidget("error", review.error_message);
      break;
  }
}

/**
 * Schedule a reconnection attempt for the commit WebSocket
 * with exponential backoff.
 */
function _scheduleCommitReconnect(commitSha) {
  if (commitWsRetries >= MERGEMIND_CONFIG.WS_MAX_RECONNECT_ATTEMPTS) {
    console.log("MergeMind: Max commit WS reconnect attempts reached");
    showWidget("timeout");
    return;
  }

  const delay = MERGEMIND_CONFIG.WS_RECONNECT_DELAY * Math.pow(2, commitWsRetries);
  commitWsRetries++;

  console.log(`MergeMind: Reconnecting commit WS in ${delay}ms (attempt ${commitWsRetries})`);
  commitWsTimer = setTimeout(() => _openCommitWs(commitSha), delay);
}

/**
 * Close the commit-level WebSocket connection.
 */
function disconnectCommitWebSocket() {
  if (commitWsTimer) {
    clearTimeout(commitWsTimer);
    commitWsTimer = null;
  }
  if (commitWs) {
    commitWs.onclose = null; // Prevent reconnect on intentional close
    commitWs.close();
    commitWs = null;
  }
}

/**
 * Open a WebSocket connection to receive real-time updates
 * for all reviews in a repository.
 *
 * The server sends the latest review state on connect,
 * then pushes updates whenever a new review is created or status changes.
 *
 * @param {string} repoFullName - "owner/repo"
 */
async function connectRepoWebSocket(repoFullName) {
  disconnectRepoWebSocket();
  repoWsRetries = 0;

  await _openRepoWs(repoFullName);
}

async function _openRepoWs(repoFullName) {
  const backendUrl = await getBackendUrl();
  const wsUrl = `${toWsUrl(backendUrl)}/ws/repo/${repoFullName}`;

  try {
    repoWs = new WebSocket(wsUrl);
  } catch (e) {
    console.error("MergeMind: Failed to create repo WebSocket:", e);
    _scheduleRepoReconnect(repoFullName);
    return;
  }

  repoWs.onopen = () => {
    console.log(`MergeMind: Repo WS connected for ${repoFullName}`);
    repoWsRetries = 0;
  };

  repoWs.onmessage = (event) => {
    if (event.data === "pong") return;

    try {
      const review = JSON.parse(event.data);
      _handleRepoUpdate(review, repoFullName);
    } catch (e) {
      console.error("MergeMind: Failed to parse repo WS message:", e);
    }
  };

  repoWs.onclose = (event) => {
    console.log(`MergeMind: Repo WS closed (code: ${event.code})`);
    repoWs = null;
    _scheduleRepoReconnect(repoFullName);
  };

  repoWs.onerror = (error) => {
    console.error("MergeMind: Repo WS error:", error);
  };
}

/**
 * Handle an incoming review update from the repo WebSocket.
 *
 * Detects new commits and opens a commit-level WS if needed.
 */
function _handleRepoUpdate(review, repoFullName) {
  if (review.status === "not_found") return;

  // If we already have a commit WS active, skip — the commit WS handles it
  if (commitWs) return;

  const isNewCommit = review.commit_sha !== currentState.commitSha;
  if (isNewCommit) {
    currentState.repo = repoFullName;
    currentState.commitSha = review.commit_sha;
    currentState.reviewData = review;
    // Reset manual close state so the new review is shown to the user!
    currentState.widgetClosed = false;
    currentState.lastWidgetState = null;

    if (review.status === "pending" || review.status === "processing") {
      connectCommitWebSocket(review.commit_sha);
    } else if (review.status === "completed") {
      showWidget("completed");
    } else if (review.status === "failed") {
      showWidget("error", review.error_message);
    }
  }
}

/**
 * Schedule a reconnection attempt for the repo WebSocket
 * with exponential backoff.
 */
function _scheduleRepoReconnect(repoFullName) {
  if (repoWsRetries >= MERGEMIND_CONFIG.WS_MAX_RECONNECT_ATTEMPTS) {
    console.log("MergeMind: Max repo WS reconnect attempts reached");
    return; // Silently stop — the repo WS is a background listener
  }

  const delay = MERGEMIND_CONFIG.WS_RECONNECT_DELAY * Math.pow(2, repoWsRetries);
  repoWsRetries++;

  console.log(`MergeMind: Reconnecting repo WS in ${delay}ms (attempt ${repoWsRetries})`);
  repoWsTimer = setTimeout(() => _openRepoWs(repoFullName), delay);
}

/**
 * Close the repo-level WebSocket connection.
 */
function disconnectRepoWebSocket() {
  if (repoWsTimer) {
    clearTimeout(repoWsTimer);
    repoWsTimer = null;
  }
  if (repoWs) {
    repoWs.onclose = null; // Prevent reconnect on intentional close
    repoWs.close();
    repoWs = null;
  }
}

/**
 * Close all WebSocket connections and clear timers.
 */
function disconnectAllWebSockets() {
  disconnectCommitWebSocket();
  disconnectRepoWebSocket();
}

/**
 * Check if a review is in a terminal state (no more updates expected).
 */
function _isTerminalState(review) {
  return review && (review.status === "completed" || review.status === "failed");
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
  disconnectCommitWebSocket();
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
  // This prevents WebSocket messages from destroying event listeners unnecessarily
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
 * Format a raw error message into a clean, user-facing format.
 *
 * If the backend already formatted the message (starts with "Error"),
 * it is used as-is. Otherwise, classify it client-side.
 *
 * @param {string} rawMsg - Raw error message
 * @returns {string} Formatted error string like "Error 429: AI RESOURCE EXHAUSTED."
 */
function formatErrorMessage(rawMsg) {
  if (!rawMsg) {
    return "Error 500: INTERNAL SERVER ERROR. An unexpected error occurred.";
  }

  // If already formatted by the backend, use as-is
  if (rawMsg.startsWith("Error ")) {
    return rawMsg;
  }

  const msg = rawMsg.toLowerCase();

  // AI / Gemini related errors
  if (msg.includes("429") || msg.includes("resource_exhausted") || msg.includes("resource exhausted")) {
    return "Error 429: AI RESOURCE EXHAUSTED. Please wait a moment and try again.";
  } else if (msg.includes("quota") || msg.includes("rate limit") || msg.includes("rate_limit")) {
    return "Error 429: AI RATE LIMIT EXCEEDED. Please try again later.";
  } else if (msg.includes("gemini") || msg.includes("genai") || msg.includes("agent")) {
    return "Error 500: AI ANALYSIS FAILED. The AI model returned an unexpected error.";
  }

  // GitHub related errors
  else if (msg.includes("401") || msg.includes("unauthorized")) {
    return "Error 401: GITHUB UNAUTHORIZED. Check your GitHub token configuration.";
  } else if (msg.includes("403") || msg.includes("forbidden")) {
    return "Error 403: GITHUB FORBIDDEN. Your token may lack the required permissions.";
  } else if (msg.includes("github") || msg.includes("diff")) {
    return "Error 502: GITHUB API ERROR. Failed to communicate with the GitHub API.";
  }

  // Fallback
  else {
    return "Error 500: INTERNAL SERVER ERROR. An unexpected error occurred.";
  }
}

/**
 * Render the error state.
 */
function renderErrorState(errorMsg) {
  const formattedError = formatErrorMessage(errorMsg);

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
        <p class="mm-error-text">Review Failed ❌</p>
        <p class="mm-error-detail">${formattedError}</p>
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

/**
 * Main initialization — runs when the content script is injected.
 * Detects GitHub context and opens WebSocket connections if applicable.
 */
async function initialize() {
  const context = detectGitHubContext();
  if (!context) {
    disconnectAllWebSockets();
    return;
  }

  currentState.repo = context.repo;

  // Start repo-level WebSocket for auto-detecting new pushes/reviews
  connectRepoWebSocket(context.repo);

  // If we're on a commit page, also open a commit-level WebSocket
  if (context.commitSha) {
    connectCommitWebSocket(context.commitSha);
    return;
  }

  // On repo pages, check for the latest review via HTTP (one-time fetch)
  const latestReview = await fetchLatestReview(context.repo);
  if (latestReview) {
    currentState.reviewData = latestReview;
    currentState.commitSha = latestReview.commit_sha;

    if (
      latestReview.status === "pending" ||
      latestReview.status === "processing"
    ) {
      // Review is still in progress — open commit WebSocket for live updates
      connectCommitWebSocket(latestReview.commit_sha);
    } else if (latestReview.status === "completed") {
      // Show the completed review
      showWidget("completed");
    }
  }
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "PAGE_UPDATED") {
    disconnectAllWebSockets();
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
