import React, { useState, useEffect } from 'react';
import Header from './components/Header';
import StatusBar from './components/StatusBar';
import Settings from './components/Settings';
import ReviewList from './components/ReviewList';
import ReviewDetail from './components/ReviewDetail';

function App() {
  const [backendUrl, setBackendUrl] = useState('http://localhost:8000');
  const [strictness, setStrictness] = useState('moderate');
  const [isConnected, setIsConnected] = useState(false);
  const [isCheckingConnection, setIsCheckingConnection] = useState(true);
  const [currentRepo, setCurrentRepo] = useState(null);
  const [reviews, setReviews] = useState([]);
  const [isLoadingReviews, setIsLoadingReviews] = useState(false);
  const [selectedReviewSha, setSelectedReviewSha] = useState(null);

  // Load configuration and detect GitHub context
  useEffect(() => {
    async function init() {
      // 1. Get settings from storage
      if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
        const data = await chrome.storage.local.get(['backendUrl', 'reviewStrictness']);
        if (data.backendUrl) setBackendUrl(data.backendUrl);
        if (data.reviewStrictness) setStrictness(data.reviewStrictness);
      }

      // 2. Detect active tab GitHub context
      if (typeof chrome !== 'undefined' && chrome.tabs) {
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        if (tab && tab.url && tab.url.includes('github.com')) {
          try {
            const pathParts = new URL(tab.url).pathname.split('/').filter(Boolean);
            if (pathParts.length >= 2) {
              const owner = pathParts[0];
              const repo = pathParts[1];
              const githubPages = [
                'settings', 'notifications', 'marketplace',
                'explore', 'topics', 'trending', 'collections',
                'sponsors', 'login', 'join', 'new'
              ];
              if (!githubPages.includes(owner)) {
                setCurrentRepo({ owner, repo, fullName: `${owner}/${repo}` });
              }
            }
          } catch (e) {
            console.error('Failed to parse active tab URL:', e);
          }
        }
      }
    }
    init();
  }, []);

  // Check connection whenever backendUrl changes
  useEffect(() => {
    let active = true;
    async function check() {
      setIsCheckingConnection(true);
      try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 4000);
        const res = await fetch(`${backendUrl}/health`, { signal: controller.signal });
        clearTimeout(timeoutId);
        if (active) {
          setIsConnected(res.ok);
        }
      } catch (err) {
        if (active) {
          setIsConnected(false);
        }
      } finally {
        if (active) {
          setIsCheckingConnection(false);
        }
      }
    }
    check();
    return () => { active = false; };
  }, [backendUrl]);

  // Load reviews for current repository when connected
  useEffect(() => {
    if (!isConnected || !currentRepo) {
      setReviews([]);
      return;
    }

    let active = true;
    async function fetchReviews() {
      setIsLoadingReviews(true);
      try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 5000);
        const res = await fetch(
          `${backendUrl}/reviews/${currentRepo.owner}?limit=10&repository=${encodeURIComponent(currentRepo.fullName)}`,
          { signal: controller.signal }
        );
        clearTimeout(timeoutId);
        if (res.ok) {
          const data = await res.json();
          if (active) {
            setReviews(data);
          }
        }
      } catch (err) {
        console.error('Failed to load reviews:', err);
      } finally {
        if (active) {
          setIsLoadingReviews(false);
        }
      }
    }
    fetchReviews();
    return () => { active = false; };
  }, [isConnected, currentRepo, backendUrl]);

  // Save backend settings
  const handleSaveSettings = async (newUrl, newStrictness) => {
    setBackendUrl(newUrl);
    setStrictness(newStrictness);

    if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
      await chrome.storage.local.set({
        backendUrl: newUrl,
        reviewStrictness: newStrictness
      });
    }

    // Sync strictness with backend if connection details are ready and user is detected
    if (currentRepo && currentRepo.owner) {
      try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 4000);
        await fetch(`${newUrl}/settings/${currentRepo.owner}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ strictness: newStrictness }),
          signal: controller.signal
        });
        clearTimeout(timeoutId);
      } catch (err) {
        console.error('Failed to sync settings to backend:', err);
      }
    }
  };

  return (
    <div className="popup-container">
      <Header />
      <StatusBar isConnected={isConnected} isChecking={isCheckingConnection} />
      
      {!selectedReviewSha ? (
        <>
          <Settings 
            backendUrl={backendUrl} 
            strictness={strictness} 
            onSave={handleSaveSettings} 
          />
          <ReviewList 
            reviews={reviews} 
            isLoading={isLoadingReviews} 
            currentRepo={currentRepo}
            onSelectReview={setSelectedReviewSha} 
          />
        </>
      ) : (
        <ReviewDetail 
          commitSha={selectedReviewSha} 
          backendUrl={backendUrl} 
          onBack={() => setSelectedReviewSha(null)} 
        />
      )}

      <footer className="popup-footer">
        <a href="https://github.com" target="_blank" rel="noreferrer" className="footer-link">GitHub</a>
        <span className="footer-sep">·</span>
        <a href={`${backendUrl}/docs`} target="_blank" rel="noreferrer" className="footer-link">API Docs</a>
      </footer>
    </div>
  );
}

export default App;
