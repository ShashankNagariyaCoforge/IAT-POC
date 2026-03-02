
import { PublicClientApplication } from '@azure/msal-browser';
import { MsalProvider, AuthenticatedTemplate, UnauthenticatedTemplate, useMsal } from '@azure/msal-react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { msalConfig, loginRequest } from './auth/msalConfig';
import CaseListPage from './pages/CaseListPage';
import CaseDetailPage from './pages/CaseDetailPage';
import './index.css';

// ─── Dev bypass ─────────────────────────────────────────────────────────────
const DEV_BYPASS_AUTH = import.meta.env.VITE_DEV_BYPASS_AUTH === 'true';
// ─────────────────────────────────────────────────────────────────────────────

const msalInstance = new PublicClientApplication(msalConfig);

function LoginPage() {
  const { instance } = useMsal();
  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', background: '#F4F6F8' }}>
      {/* Top utility bar matching IAT website */}
      <div style={{ background: '#1E3E5C', padding: '8px 32px', display: 'flex', justifyContent: 'flex-end', gap: '24px' }}>
        <span style={{ color: '#cdd8e2', fontSize: '12px' }}>Agent &amp; Brokers</span>
        <span style={{ color: '#cdd8e2', fontSize: '12px' }}>Contact Us</span>
      </div>

      {/* Main navbar */}
      <div style={{ background: '#ffffff', borderBottom: '1px solid #D1D9E0', padding: '12px 32px' }}>
        <img src="/assets/iat-logo.png" alt="IAT Insurance Group" style={{ height: '48px', width: 'auto', objectFit: 'contain' }} />
      </div>

      {/* Login card */}
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '48px 16px' }}>
        <div style={{
          background: '#ffffff',
          border: '1px solid #D1D9E0',
          borderRadius: '8px',
          padding: '48px 40px',
          width: '100%',
          maxWidth: '420px',
          textAlign: 'center',
          boxShadow: '0 4px 24px rgba(0,38,62,0.08)',
        }}>
          <img src="/assets/iat-logo.png" alt="IAT Insurance Group" style={{ height: '52px', width: 'auto', objectFit: 'contain', marginBottom: '24px' }} />
          <h1 style={{ color: '#00263E', fontSize: '22px', fontWeight: 700, margin: '0 0 6px 0' }}>AI Email Automation</h1>
          <p style={{ color: '#5a7184', fontSize: '14px', margin: '0 0 28px 0' }}>Sign in with your organisation account to access the case management portal.</p>
          <button
            onClick={() => instance.loginRedirect(loginRequest)}
            style={{
              width: '100%',
              background: '#00467F',
              color: '#ffffff',
              border: 'none',
              borderRadius: '6px',
              padding: '13px 24px',
              fontSize: '15px',
              fontWeight: 600,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '10px',
              transition: 'background 0.2s',
            }}
            onMouseEnter={e => (e.currentTarget.style.background = '#005099')}
            onMouseLeave={e => (e.currentTarget.style.background = '#00467F')}
          >
            <svg style={{ width: '18px', height: '18px' }} viewBox="0 0 21 21" fill="none">
              <rect x="1" y="1" width="9" height="9" fill="#f25022" />
              <rect x="11" y="1" width="9" height="9" fill="#7fba00" />
              <rect x="1" y="11" width="9" height="9" fill="#00a4ef" />
              <rect x="11" y="11" width="9" height="9" fill="#ffb900" />
            </svg>
            Sign in with Microsoft
          </button>
          <p style={{ color: '#8fa1b0', fontSize: '11px', marginTop: '20px' }}>Secured by Azure Active Directory</p>
        </div>
      </div>

      {/* Footer bar */}
      <div style={{ background: '#00263E', padding: '12px 32px', textAlign: 'center' }}>
        <span style={{ color: '#7a9bb0', fontSize: '12px' }}>© IAT Insurance Group. All rights reserved.</span>
      </div>
    </div>
  );
}

function AppRoutes() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<CaseListPage />} />
        <Route path="/cases/:caseId" element={<CaseDetailPage />} />
      </Routes>
    </BrowserRouter>
  );
}

function AppRoutesWithAuth() {
  return (
    <BrowserRouter>
      <AuthenticatedTemplate>
        <Routes>
          <Route path="/" element={<CaseListPage />} />
          <Route path="/cases/:caseId" element={<CaseDetailPage />} />
        </Routes>
      </AuthenticatedTemplate>
      <UnauthenticatedTemplate>
        <LoginPage />
      </UnauthenticatedTemplate>
    </BrowserRouter>
  );
}

export default function App() {
  if (DEV_BYPASS_AUTH) {
    return <AppRoutes />;
  }
  return (
    <MsalProvider instance={msalInstance}>
      <AppRoutesWithAuth />
    </MsalProvider>
  );
}
