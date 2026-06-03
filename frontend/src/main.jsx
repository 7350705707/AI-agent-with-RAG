import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css';

// ── HTTPS enforcement ─────────────────────────────────────────────────────
// In production (non-localhost), silently redirect plain HTTP to HTTPS.
// if (
//   window.location.protocol === 'http:' &&
//   window.location.hostname !== 'localhost' &&
//   window.location.hostname !== '127.0.0.1'
// ) {
//   window.location.replace(
//     window.location.href.replace(/^http:/, 'https:')
//   );
// } else {
  ReactDOM.createRoot(document.getElementById('root')).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>
  );
// }
