import { useState } from 'react';
import { PublicClientApplication, InteractionStatus } from '@azure/msal-browser';
import { MsalProvider, useMsal } from '@azure/msal-react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { msalConfig, loginRequest } from './auth/msalConfig';

// Pages
import CommandCenterPage from './pages/CommandCenterPage';
import CaseActionScreen from './pages/CaseActionScreen';
import CaseSnapshotPage from './pages/CaseSnapshotPage';
// import ExtractionReviewPage from './pages/ExtractionReviewPage';

// Contexts
import { PipelineProvider } from './contexts/PipelineContext';

import { Mail, Fingerprint, ShieldCheck, BrainCircuit, ArrowRight, Lock, Activity, Loader2, FileText, Globe } from 'lucide-react';
import './index.css';

// ─── Dev bypass ─────────────────────────────────────────────────────────────
const DEV_BYPASS_AUTH = import.meta.env.VITE_DEV_BYPASS_AUTH === 'true';
// ─────────────────────────────────────────────────────────────────────────────

const msalInstance = new PublicClientApplication(msalConfig);

function LoginView({ onLogin, onDevMode }: { onLogin: () => void, onDevMode: () => void }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loginError, setLoginError] = useState(false);

  const handleCredentialLogin = () => {
    if (username === 'admin' && password === 'Secura123') {
      setLoginError(false);
      onDevMode();
    } else {
      setLoginError(true);
    }
  };

  const features = [
    { icon: <Mail size={15} />, text: 'Email Agent — Automatic intake & parsing' },
    { icon: <Fingerprint size={15} />, text: 'PII Agent — Real-time data masking' },
    { icon: <ShieldCheck size={15} />, text: 'Content Safety Agent — Policy compliance' },
    { icon: <BrainCircuit size={15} />, text: 'Classification Agent — AI-driven triage' },
    { icon: <FileText size={15} />, text: 'Extraction Agent — Structured field extraction' },
    { icon: <Globe size={15} />, text: 'Enrichment Agent — Web-sourced entity data' },
  ];

  return (
    <div style={{
      minHeight: '100vh', background: '#f8fafc',
      display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '24px',
    }}>
      {/* Card */}
      <div style={{
        width: '100%', maxWidth: '1000px',
        display: 'grid', gridTemplateColumns: '1fr 1fr',
        background: '#ffffff', borderRadius: '40px',
        overflow: 'hidden',
        boxShadow: '0 40px 80px -20px rgba(0,0,0,0.14), 0 0 0 1px rgba(0,0,0,0.04)',
      }}>

        {/* ── Left dark panel ── */}
        <div style={{
          background: 'linear-gradient(160deg, #1c1c1e 60%, #2d1a00)',
          padding: '52px 48px',
          display: 'flex', flexDirection: 'column', justifyContent: 'space-between',
          position: 'relative', overflow: 'hidden',
        }}>
          {/* Ambient blobs */}
          <div style={{ position: 'absolute', top: '-40px', right: '-40px', width: '200px', height: '200px', background: 'rgba(232,119,34,0.18)', borderRadius: '50%', filter: 'blur(80px)' }} />
          <div style={{ position: 'absolute', bottom: '-40px', left: '-40px', width: '180px', height: '180px', background: 'rgba(180,80,10,0.15)', borderRadius: '50%', filter: 'blur(80px)' }} />

          {/* Top section */}
          <div style={{ position: 'relative' }}>
            {/* Logo */}
            <div style={{ display: 'inline-flex', alignItems: 'center', marginBottom: '40px', background: '#ffffff', borderRadius: '10px', padding: '7px 16px' }}>
              <img src="/assets/secura-logo.png" alt="Secura" style={{ height: '28px' }} />
            </div>

            <h2 style={{
              color: '#ffffff', fontSize: '32px', fontWeight: 900,
              margin: '0 0 14px 0', lineHeight: 1.15, letterSpacing: '-0.02em',
            }}>
              AI-Powered<br />Underwriting<br />Command Center.
            </h2>
            <p style={{ color: 'rgba(255,255,255,0.45)', fontSize: '14px', margin: '0 0 32px 0', lineHeight: 1.6, fontWeight: 400 }}>
              Access your agentic intake pipeline. Six specialized AI agents process
              every submission with neural-precision.
            </p>

            {/* Feature list */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              {features.map((f, i) => (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <div style={{
                    width: '30px', height: '30px', borderRadius: '8px',
                    background: 'rgba(232,119,34,0.2)', border: '1px solid rgba(232,119,34,0.35)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    color: '#E87722', flexShrink: 0,
                  }}>{f.icon}</div>
                  <span style={{ color: 'rgba(255,255,255,0.65)', fontSize: '13px', fontWeight: 500 }}>{f.text}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Bottom section */}
          <div style={{ position: 'relative', paddingTop: '24px', borderTop: '1px solid rgba(255,255,255,0.08)' }}>
            <div style={{
              background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)',
              borderRadius: '14px', padding: '14px 18px', marginBottom: '16px',
            }}>
              <p style={{ margin: '0 0 4px 0', fontSize: '9px', fontWeight: 800, color: '#E87722', textTransform: 'uppercase', letterSpacing: '0.12em' }}>Live System Status</p>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <div style={{ width: '7px', height: '7px', borderRadius: '50%', background: '#22c55e', boxShadow: '0 0 8px #22c55e' }} />
                <span style={{ color: 'rgba(255,255,255,0.6)', fontSize: '12px', fontWeight: 500 }}>All 6 agents operational</span>
              </div>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Lock size={12} style={{ color: 'rgba(255,255,255,0.3)' }} />
              <span style={{ color: 'rgba(255,255,255,0.3)', fontSize: '11px' }}>End-to-end encrypted · SOC-2 compliant</span>
            </div>
          </div>
        </div>

        {/* ── Right white form panel ── */}
        <div style={{ padding: '52px 52px', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
          <div style={{ maxWidth: '360px', margin: '0 auto', width: '100%' }}>
            <div style={{ marginBottom: '36px' }}>
              <h3 style={{ color: '#0f172a', fontSize: '26px', fontWeight: 900, margin: '0 0 6px 0', letterSpacing: '-0.02em' }}>
                Sign In
              </h3>
              <p style={{ color: '#94a3b8', fontSize: '14px', margin: 0, fontWeight: 500 }}>
                Authenticate with your organisation account
              </p>
            </div>

            {/* Microsoft SSO button */}
            <button
              onClick={onLogin}
              style={{
                width: '100%', background: '#0f172a', color: '#ffffff', border: 'none',
                borderRadius: '14px', padding: '15px 20px', fontSize: '14px', fontWeight: 700,
                cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
                gap: '10px', marginBottom: '12px', letterSpacing: '0.01em',
                boxShadow: '0 8px 24px rgba(15,23,42,0.18)',
                transition: 'all 0.2s',
              }}
              onMouseEnter={e => (e.currentTarget.style.background = '#E87722')}
              onMouseLeave={e => (e.currentTarget.style.background = '#0f172a')}
            >
              <svg style={{ width: '18px', height: '18px', flexShrink: 0 }} viewBox="0 0 21 21" fill="none">
                <rect x="1" y="1" width="9" height="9" fill="#f25022" />
                <rect x="11" y="1" width="9" height="9" fill="#7fba00" />
                <rect x="1" y="11" width="9" height="9" fill="#00a4ef" />
                <rect x="11" y="11" width="9" height="9" fill="#ffb900" />
              </svg>
              Sign in with Microsoft
              <ArrowRight size={16} style={{ marginLeft: 'auto' }} />
            </button>

            {/* Divider */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', margin: '4px 0' }}>
              <div style={{ flex: 1, height: '1px', background: '#e2e8f0' }} />
              <span style={{ fontSize: '11px', color: '#94a3b8', fontWeight: 600 }}>or</span>
              <div style={{ flex: 1, height: '1px', background: '#e2e8f0' }} />
            </div>

            {/* Username / Password form */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              <input
                type="text"
                placeholder="Username"
                value={username}
                onChange={e => { setUsername(e.target.value); setLoginError(false); }}
                onKeyDown={e => e.key === 'Enter' && handleCredentialLogin()}
                style={{
                  width: '100%', boxSizing: 'border-box',
                  padding: '13px 16px', borderRadius: '12px', fontSize: '14px', fontWeight: 500,
                  border: loginError ? '1.5px solid #fca5a5' : '1.5px solid #e2e8f0',
                  outline: 'none', color: '#0f172a', background: '#f8fafc',
                }}
              />
              <input
                type="password"
                placeholder="Password"
                value={password}
                onChange={e => { setPassword(e.target.value); setLoginError(false); }}
                onKeyDown={e => e.key === 'Enter' && handleCredentialLogin()}
                style={{
                  width: '100%', boxSizing: 'border-box',
                  padding: '13px 16px', borderRadius: '12px', fontSize: '14px', fontWeight: 500,
                  border: loginError ? '1.5px solid #fca5a5' : '1.5px solid #e2e8f0',
                  outline: 'none', color: '#0f172a', background: '#f8fafc',
                }}
              />
              {loginError && (
                <p style={{ margin: 0, fontSize: '12px', color: '#ef4444', fontWeight: 600 }}>
                  Invalid username or password.
                </p>
              )}
              <button
                onClick={handleCredentialLogin}
                style={{
                  width: '100%', background: '#E87722', color: '#ffffff', border: 'none',
                  borderRadius: '12px', padding: '13px 20px', fontSize: '14px', fontWeight: 700,
                  cursor: 'pointer', transition: 'all 0.2s',
                }}
                onMouseEnter={e => (e.currentTarget.style.background = '#c96510')}
                onMouseLeave={e => (e.currentTarget.style.background = '#E87722')}
              >
                Login
              </button>
            </div>

            {/* Security notice */}
            <div style={{
              marginTop: '28px', padding: '14px 18px',
              background: '#fffbeb', border: '1px solid #fde68a',
              borderRadius: '12px', display: 'flex', alignItems: 'flex-start', gap: '10px',
            }}>
              <Activity size={15} style={{ color: '#d97706', flexShrink: 0, marginTop: '1px' }} />
              <div>
                <p style={{ margin: '0 0 2px 0', fontSize: '9px', fontWeight: 800, color: '#92400e', textTransform: 'uppercase', letterSpacing: '0.1em' }}>Security Notice</p>
                <p style={{ margin: 0, fontSize: '11px', color: '#78350f', lineHeight: 1.5, fontWeight: 500 }}>
                  Authorised underwriting staff only. All activity is monitored per compliance protocol.
                </p>
              </div>
            </div>

            <p style={{ color: '#cbd5e1', fontSize: '11px', marginTop: '20px', textAlign: 'center' }}>
              Secured by Azure Active Directory
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

function AuthenticatedApp({ onDevMode, useDevBypass }: { onDevMode: () => void, useDevBypass: boolean }) {
  const { instance, accounts, inProgress } = useMsal();
  const isAuthenticated = accounts.length > 0;

  if (inProgress === InteractionStatus.Login || inProgress === InteractionStatus.HandleRedirect) {
    return (
      <div className="flex h-screen items-center justify-center bg-gray-50">
        <div className="flex flex-col items-center gap-4 text-gray-500">
          <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
          <p className="text-sm font-medium">Signing in via Azure AD...</p>
        </div>
      </div>
    );
  }

  if (inProgress === InteractionStatus.None && !isAuthenticated && !useDevBypass) {
    return <LoginView onLogin={() => instance.loginRedirect(loginRequest)} onDevMode={onDevMode} />;
  }

  return (
    <PipelineProvider>
      <div className="min-h-screen bg-gray-50 pb-8">
        <Routes>
          <Route path="/" element={<CommandCenterPage />} />
          <Route path="/cases/:caseId" element={<CaseActionScreen />} />
          {/* <Route path="/cases/:caseId/review" element={<ExtractionReviewPage />} /> */}
          <Route path="/cases/:caseId/snapshot" element={<CaseSnapshotPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </div>
    </PipelineProvider>
  );
}

export default function App() {
  const [useDevBypass, setUseDevBypass] = useState(
    DEV_BYPASS_AUTH || localStorage.getItem('dev_bypass') === 'true'
  );

  const handleDevMode = () => {
    localStorage.setItem('dev_bypass', 'true');
    setUseDevBypass(true);
  };

  return (
    <MsalProvider instance={msalInstance}>
      <BrowserRouter>
        <AuthenticatedApp onDevMode={handleDevMode} useDevBypass={useDevBypass} />
      </BrowserRouter>
    </MsalProvider>
  );
}
