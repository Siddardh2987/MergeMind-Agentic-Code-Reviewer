import React from 'react';

function StatusBar({ isConnected, isChecking }) {
  let statusClass = 'status-dot';
  let statusText = 'Checking connection...';

  if (!isChecking) {
    if (isConnected) {
      statusClass += ' connected';
      statusText = 'Connected to backend';
    } else {
      statusClass += ' disconnected';
      statusText = 'Backend unreachable';
    }
  }

  return (
    <div className="popup-status">
      <div className={statusClass}></div>
      <span className="status-text">{statusText}</span>
    </div>
  );
}

export default StatusBar;
