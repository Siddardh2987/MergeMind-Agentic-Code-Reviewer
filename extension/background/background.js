/**
 * MergeMind — Background Service Worker
 *
 * Runs in the background and handles:
 *   • Listening for tab URL changes on GitHub
 *   • Communicating with content scripts
 *   • Managing extension badge/icon state
 *
 * Manifest V3 uses service workers instead of persistent background pages.
 * Service workers are event-driven and don't maintain persistent state.
 */

// ── Listen for Tab Updates ──────────────────────────────────────────
// When a user navigates to a GitHub page, notify the content script
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  // Capture either explicit URL changes or page completion loads
  if (!changeInfo.url && changeInfo.status !== "complete") return;

  // Only process GitHub URLs
  if (!tab.url || !tab.url.includes("github.com")) return;

  // Send a message to the content script to check for reviews
  chrome.tabs.sendMessage(tabId, {
    type: "PAGE_UPDATED",
    url: tab.url,
  }).catch(() => {
    // Content script might not be loaded yet — that's OK
  });
});

// ── Listen for Messages from Content Script ──────────────────────────
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "GET_BACKEND_URL") {
    // Content script is requesting the backend URL
    // (In case config.js isn't loaded yet)
    chrome.storage.local.get(["backendUrl"], (result) => {
      sendResponse({
        backendUrl: result.backendUrl || "http://localhost:8000",
      });
    });
    return true; // Keep the message channel open for async response
  }

  if (message.type === "REVIEW_STATUS_UPDATE") {
    // Content script is reporting a review status change
    // Update the extension badge to reflect the status
    const tabId = sender.tab?.id;
    if (!tabId) return;

    switch (message.status) {
      case "pending":
      case "processing":
        // Yellow badge = review in progress
        chrome.action.setBadgeBackgroundColor({ color: "#F59E0B", tabId });
        chrome.action.setBadgeText({ text: "⏳", tabId });
        break;
      case "completed":
        // Green or red badge based on issue count
        const hasIssues = message.issueCount > 0;
        chrome.action.setBadgeBackgroundColor({
          color: hasIssues ? "#EF4444" : "#10B981",
          tabId,
        });
        chrome.action.setBadgeText({
          text: hasIssues ? String(message.issueCount) : "✓",
          tabId,
        });
        break;
      case "failed":
        // Red badge = review failed
        chrome.action.setBadgeBackgroundColor({ color: "#EF4444", tabId });
        chrome.action.setBadgeText({ text: "!", tabId });
        break;
      default:
        chrome.action.setBadgeText({ text: "", tabId });
    }
  }
});

// ── Extension Install/Update Handler ─────────────────────────────────
chrome.runtime.onInstalled.addListener((details) => {
  if (details.reason === "install") {
    console.log("🧠 MergeMind installed successfully!");

    // Set default backend URL in storage
    chrome.storage.local.set({
      backendUrl: "http://localhost:8000",
    });
  }
});
