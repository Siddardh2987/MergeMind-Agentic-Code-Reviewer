import React, { useState, useEffect } from 'react';

function Settings({ backendUrl, strictness, onSave }) {
  const [urlInput, setUrlInput] = useState(backendUrl);
  const [selectedStrictness, setSelectedStrictness] = useState(strictness);
  const [isSaved, setIsSaved] = useState(false);

  // Sync state with props
  useEffect(() => {
    setUrlInput(backendUrl);
    setSelectedStrictness(strictness);
  }, [backendUrl, strictness]);

  const handleSave = () => {
    const trimmed = urlInput.trim().replace(/\/$/, '');
    if (!trimmed) return;
    
    onSave(trimmed, selectedStrictness);
    setIsSaved(true);
    setTimeout(() => {
      setIsSaved(false);
    }, 2000);
  };

  return (
    <section className="popup-section">
      <h2 className="section-title">⚙️ Settings</h2>
      
      <div className="setting-group">
        <label className="setting-label" htmlFor="backend-url">Backend URL</label>
        <div className="setting-input-group">
          <input
            type="url"
            id="backend-url"
            className={`setting-input ${!urlInput.trim() ? 'error' : ''}`}
            placeholder="http://localhost:8000"
            value={urlInput}
            onChange={(e) => setUrlInput(e.target.value)}
          />
          <button 
            className={`setting-save-btn ${isSaved ? 'saved' : ''}`} 
            onClick={handleSave} 
            title="Save Settings"
          >
            {isSaved ? '✓' : 'Save'}
          </button>
        </div>
      </div>

      <div className="setting-group">
        <label className="setting-label">Review Strictness</label>
        <div className="strictness-options">
          {['lenient', 'moderate', 'strict'].map((level) => (
            <button
              key={level}
              type="button"
              className={`strictness-btn ${level} ${selectedStrictness === level ? 'active' : ''}`}
              onClick={() => setSelectedStrictness(level)}
            >
              {level.charAt(0).toUpperCase() + level.slice(1)}
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}

export default Settings;
