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

  // ── Polling Configuration ────────────────────────────────────────
  // How often to poll for review status (in milliseconds)
  POLL_INTERVAL: 5000, // 5 seconds

  // Maximum number of poll attempts before giving up
  MAX_POLL_ATTEMPTS: 60, // 60 × 5s = 5 minutes max wait

  // ── UI Configuration ─────────────────────────────────────────────
  // How long to show the notification widget before auto-minimizing (ms)
  AUTO_MINIMIZE_DELAY: 30000, // 30 seconds

  // Animation duration for expand/collapse (ms)
  ANIMATION_DURATION: 300,
};
