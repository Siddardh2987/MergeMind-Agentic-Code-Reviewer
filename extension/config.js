/**
 * MergeMind — Extension Configuration
 *
 * Central configuration file for the Chrome extension.
 * Update BACKEND_URL after deploying the backend to production.
 */

const MERGEMIND_CONFIG = {
  // ── Backend API URL ──────────────────────────────────────────────
  // Default: local development server
  // Update this after deploying to Render/Railway/etc.
  BACKEND_URL: "http://localhost:8000",

  // ── WebSocket Configuration ─────────────────────────────────────
  // Initial delay before reconnecting after a WebSocket drop (ms)
  WS_RECONNECT_DELAY: 1000, // 1 second (doubles each retry via exponential backoff)

  // Maximum number of reconnection attempts before giving up
  WS_MAX_RECONNECT_ATTEMPTS: 10,

  // ── UI Configuration ─────────────────────────────────────────────
  // How long to show the notification widget before auto-minimizing (ms)
  AUTO_MINIMIZE_DELAY: 30000, // 30 seconds

  // Animation duration for expand/collapse (ms)
  ANIMATION_DURATION: 300,
};
