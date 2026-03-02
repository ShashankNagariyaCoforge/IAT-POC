import React from 'react';
import { PublicClientApplication } from '@azure/msal-browser';
import { MsalProvider, AuthenticatedTemplate, UnauthenticatedTemplate, useMsal } from '@azure/msal-react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { msalConfig, loginRequest } from './auth/msalConfig';
import CaseListPage from './pages/CaseListPage';
import CaseDetailPage from './pages/CaseDetailPage';
import './index.css';

// ─── Dev bypass ────────────────────────────────────────────────────────────────
// Set VITE_DEV_BYPASS_AUTH=true in your .env.local to skip Azure AD login.
// Remove / set to false before deploying to production.
const DEV_BYPASS_AUTH = import.meta.env.VITE_DEV_BYPASS_AUTH === 'true';
// ───────────────────────────────────────────────────────────────────────────────

const msalInstance = new PublicClientApplication(msalConfig);

function LoginPage() {
  const { instance } = useMsal();
  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-950">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl p-10 w-full max-w-md text-center shadow-2xl">
        <div className="mb-6">
          <div className="w-16 h-16 bg-blue-600 rounded-2xl flex items-center justify-center mx-auto mb-4">
            <svg className="w-9 h-9 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
            </svg>
          </div>
          <h1 className="text-2xl font-bold text-white">IAT Insurance</h1>
          <p className="text-slate-400 mt-1 text-sm">AI Email Automation Platform</p>
        </div>
        <p className="text-slate-300 mb-8 text-sm">Sign in with your organisation account to access the case management portal.</p>
        <button
          onClick={() => instance.loginRedirect(loginRequest)}
          className="w-full bg-blue-600 hover:bg-blue-500 text-white font-semibold py-3 px-6 rounded-xl
                     transition-all duration-200 flex items-center justify-center gap-3"
        >
          <svg className="w-5 h-5" viewBox="0 0 21 21" fill="none">
            <rect x="1" y="1" width="9" height="9" fill="#f25022" />
            <rect x="11" y="1" width="9" height="9" fill="#7fba00" />
            <rect x="1" y="11" width="9" height="9" fill="#00a4ef" />
            <rect x="11" y="11" width="9" height="9" fill="#ffb900" />
          </svg>
          Sign in with Microsoft
        </button>
        <p className="text-slate-600 text-xs mt-6">Secured by Azure Active Directory</p>
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
  // Dev mode: skip MSAL entirely and render routes directly
  if (DEV_BYPASS_AUTH) {
    return <AppRoutes />;
  }

  return (
    <MsalProvider instance={msalInstance}>
      <AppRoutesWithAuth />
    </MsalProvider>
  );
}
