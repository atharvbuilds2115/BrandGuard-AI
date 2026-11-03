import { useRef, useState, type FormEvent } from 'react';
import {
  AlertCircle,
  Eye,
  EyeOff,
  LoaderCircle,
  LockKeyhole,
  ShieldCheck,
} from 'lucide-react';
import {
  loginWithEmail,
  loginWithGoogle,
  registerWithEmail,
  resetPassword,
  demoLoginCredentials,
} from '../lib/firebase';
import { useNavigate } from 'react-router-dom';
import './AuthScreen.css';

type AuthScreenProps = {
  firebaseConfigState: 'missing' | 'partial' | 'configured';
};

type AuthAction = 'email' | 'google' | 'reset' | 'demo' | null;
type AuthOperation = 'login' | 'register' | 'google' | 'reset';

const currentYear = new Date().getFullYear();

function friendlyAuthError(error: unknown, operation: AuthOperation): string {
  const code =
    typeof error === 'object' && error !== null && 'code' in error
      ? String(error.code)
      : '';
  const messages: Record<string, string> = {
    'auth/email-already-in-use': 'An account already exists for this email. If you created it with Google, choose Continue with Google; Google sign-in does not automatically create a password.',
    'auth/invalid-email': 'Enter a valid email address.',
    'auth/invalid-credential': 'Email/password sign-in was not accepted. Check your email and password. If this account was created with Google, choose Continue with Google; Google sign-in does not automatically create a password.',
    'auth/invalid-login-credentials': 'Email/password sign-in was not accepted. Check your email and password. If this account was created with Google, choose Continue with Google; Google sign-in does not automatically create a password.',
    'auth/wrong-password': 'The password is incorrect. If this account was created with Google, choose Continue with Google; Google sign-in does not automatically create a password.',
    'auth/user-disabled': 'This account has been disabled. Contact your administrator.',
    'auth/too-many-requests': 'Too many attempts. Wait a little and try again.',
    'auth/quota-exceeded': 'Firebase temporarily limited this request. Wait a little and try again.',
    'auth/weak-password': 'Firebase rejected this password as too weak. Choose a stronger password that meets the project password policy.',
    'auth/user-not-found': 'Firebase could not find an account for this email address.',
    'auth/missing-email': 'Enter your email address and try again.',
    'auth/missing-password': 'Enter your password and try again.',
    'auth/operation-not-allowed': 'Email/password authentication is disabled for this Firebase project. Enable the Email/Password provider in Firebase Console.',
    'auth/network-request-failed': 'We could not reach Firebase. Check your connection and try again.',
    'auth/popup-closed-by-user': 'Google sign-in was cancelled. You can try again whenever you are ready.',
    'auth/popup-blocked': `Google sign-in could not open. Allow pop-ups and check that ${window.location.hostname} is listed in Firebase Authentication authorized domains.`,
    'auth/cancelled-popup-request': 'A Google sign-in window is already open. Complete it or try again.',
    'auth/account-exists-with-different-credential':
      'An account already exists with this email. Sign in using its existing method.',
    'auth/unauthorized-domain': `This site (${window.location.hostname}) is not authorized for Firebase sign-in. Add it in Firebase Authentication authorized domains.`,
    'auth/invalid-api-key': 'Firebase configuration is invalid. Check the project web app settings.',
    'auth/invalid-app-credential': 'Google sign-in configuration is invalid. Check the Google provider settings in Firebase Console.',
  };
  if (messages[code]) return `${messages[code]} (${code}).`;
  if (code === 'auth/user-not-found') {
    const message = operation === 'reset'
      ? 'Firebase could not find an account for this email address.'
      : 'Firebase could not find an account for this email and password. If this account was created with Google, choose Continue with Google.';
    return `${message} (${code}).`;
  }

  const detail = error instanceof Error
    ? error.message
      .replace(/^Firebase:\s*/i, '')
      .replace(/\s+\(auth\/[^)]+\)\.?$/i, '')
      .trim()
    : '';
  if (detail) return code ? `${detail} (${code}).` : detail;
  return code ? `Authentication failed (${code}). Please try again.` : 'We could not complete sign-in. Please try again.';
}

function isValidEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

function GoogleMark() {
  return (
    <svg aria-hidden="true" viewBox="0 0 48 48" className="auth-google-mark">
      <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5Z" transform="translate(0 4)" />
      <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.27 5.47-4.76 7.16l7.73 6C44.42 38.02 46.98 31.91 46.98 24.55Z" transform="translate(0 0)" />
      <path fill="#FBBC05" d="M10.53 28.59a14.4 14.4 0 0 1 0-9.18l-7.98-6.19a23.95 23.95 0 0 0 0 21.56l7.98-6.19Z" transform="translate(0 4)" />
      <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.91-5.82l-7.73-6c-2.15 1.45-4.92 2.3-8.18 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48Z" transform="translate(0 -4)" />
    </svg>
  );
}

export default function AuthScreen({ firebaseConfigState }: AuthScreenProps) {
  const navigate = useNavigate();
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [action, setAction] = useState<AuthAction>(null);
  const actionLock = useRef(false);
  const firebaseReady = firebaseConfigState === 'configured';
  const demoCredentials = demoLoginCredentials;

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError('');
    setNotice('');
    if (!firebaseReady) {
      setError('Configure Firebase before signing in or creating an account.');
      return;
    }
    if (actionLock.current) return;
    const trimmedEmail = email.trim();
    if (!isValidEmail(trimmedEmail)) {
      setError('Enter a valid email address.');
      return;
    }
    if (!password) {
      setError('Enter your password.');
      return;
    }
    if (mode === 'register' && password.length < 8) {
      setError('Use a password with at least 8 characters.');
      return;
    }
    if (mode === 'register' && password !== confirmPassword) {
      setError('The passwords do not match.');
      return;
    }

    actionLock.current = true;
    setAction('email');
    try {
      if (mode === 'register') {
        await registerWithEmail(trimmedEmail, password);
      } else {
        await loginWithEmail(trimmedEmail, password);
      }
      navigate('/dashboard', { replace: true });
    } catch (submitError) {
      setError(friendlyAuthError(submitError, mode));
      actionLock.current = false;
      setAction(null);
    }
  };

  const handleGoogleSignIn = async () => {
    setError('');
    setNotice('');
    if (!firebaseReady) {
      setError('Configure Firebase before signing in.');
      return;
    }
    if (actionLock.current) return;

    actionLock.current = true;
    setAction('google');
    try {
      await loginWithGoogle();
      navigate('/dashboard', { replace: true });
    } catch (signInError) {
      setError(friendlyAuthError(signInError, 'google'));
      actionLock.current = false;
      setAction(null);
    }
  };

  const handleDemoLogin = async () => {
    setError('');
    setNotice('');
    if (!demoLoginCredentials) return;
    if (!firebaseReady) {
      setError('Configure Firebase before signing in to the demo workspace.');
      return;
    }
    if (actionLock.current) return;

    actionLock.current = true;
    setAction('demo');
    try {
      const user = await loginWithEmail(demoLoginCredentials.email, demoLoginCredentials.password);
      await user.getIdToken();
      navigate('/dashboard', { replace: true });
    } catch (signInError) {
      setError(friendlyAuthError(signInError, 'login'));
      actionLock.current = false;
      setAction(null);
    }
  };

  const handlePasswordReset = async () => {
    setError('');
    setNotice('');
    const trimmedEmail = email.trim();
    if (!isValidEmail(trimmedEmail)) {
      setError('Enter your email address above to receive a password reset link.');
      return;
    }
    if (!firebaseReady) {
      setError('Configure Firebase before requesting a password reset.');
      return;
    }
    if (actionLock.current) return;

    actionLock.current = true;
    setAction('reset');
    try {
      await resetPassword(trimmedEmail);
      setNotice('Firebase accepted the password reset request. Email delivery is not guaranteed; if this address has an account, check its inbox and spam folder.');
      actionLock.current = false;
      setAction(null);
    } catch (resetError) {
      setError(friendlyAuthError(resetError, 'reset'));
      actionLock.current = false;
      setAction(null);
    }
  };

  const toggleMode = () => {
    setMode((current) => current === 'login' ? 'register' : 'login');
    setError('');
    setNotice('');
    setPassword('');
    setConfirmPassword('');
  };

  return (
    <main className="auth-page">
      <section className="auth-card" aria-labelledby="auth-heading">
        <header className="auth-brand">
          <span className="auth-brand-icon"><ShieldCheck size={23} strokeWidth={2.2} /></span>
          <span className="auth-brand-name">BRANDGUARD AI</span>
          <span className="auth-brand-subtitle">Your AI Brand Safety Workspace</span>
        </header>

        <div className="auth-heading-block">
          <h1 id="auth-heading">{mode === 'login' ? 'Sign in' : 'Create your account'}</h1>
          <p>
            {mode === 'login'
              ? 'Use your email and password to access your workspace.'
              : 'Get started with your secure brand workspace.'}
          </p>
        </div>

        {!firebaseReady && (
          <div role="status" className="auth-config-notice">
            <strong>Firebase setup required</strong>
            <p>Add the project web app values to <code>.env.local</code>, then restart the app:</p>
            <ul>
              <li>VITE_FIREBASE_API_KEY</li>
              <li>VITE_FIREBASE_AUTH_DOMAIN</li>
              <li>VITE_FIREBASE_PROJECT_ID</li>
              <li>VITE_FIREBASE_APP_ID</li>
            </ul>
            <p>Enable Email/Password and Google providers in Firebase Authentication.</p>
          </div>
        )}

        <form onSubmit={handleSubmit} noValidate className="auth-form">
          <div className="auth-field">
            <label htmlFor="auth-email">Email</label>
            <input
              id="auth-email"
              type="email"
              autoComplete="email"
              autoCapitalize="none"
              spellCheck={false}
              placeholder="you@company.com"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </div>

          <div className="auth-field">
            <div className="auth-label-row">
              <label htmlFor="auth-password">Password</label>
              {mode === 'login' && (
                <button type="button" className="auth-text-button" onClick={() => void handlePasswordReset()} disabled={Boolean(action)}>
                  {action === 'reset' ? 'Sending link…' : 'Forgot password?'}
                </button>
              )}
            </div>
            <div className="auth-password-wrap">
              <input
                id="auth-password"
                type={showPassword ? 'text' : 'password'}
                autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                minLength={mode === 'register' ? 8 : undefined}
                required
                placeholder="Enter your password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
              <button
                type="button"
                className="auth-password-toggle"
                aria-label={showPassword ? 'Hide password' : 'Show password'}
                aria-pressed={showPassword}
                onClick={() => setShowPassword((visible) => !visible)}
              >
                {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
            {mode === 'register' && <p className="auth-field-hint">Use at least 8 characters.</p>}
          </div>

          {mode === 'register' && (
            <div className="auth-field">
              <label htmlFor="auth-confirm-password">Confirm password</label>
              <input
                id="auth-confirm-password"
                type={showPassword ? 'text' : 'password'}
                autoComplete="new-password"
                minLength={8}
                required
                placeholder="Enter your password again"
                value={confirmPassword}
                onChange={(event) => setConfirmPassword(event.target.value)}
              />
            </div>
          )}

          {error && (
            <p role="alert" className="auth-message auth-error">
              <AlertCircle size={17} /> <span>{error}</span>
            </p>
          )}
          {notice && <p role="status" className="auth-message auth-success">{notice}</p>}

          <button type="submit" className="auth-primary-button" disabled={Boolean(action)}>
            {action === 'email' ? <LoaderCircle size={18} className="auth-spinner" /> : null}
            {action === 'email' ? 'Please wait…' : mode === 'login' ? 'Sign In' : 'Create account'}
          </button>
        </form>

        <div className="auth-divider"><span /> <span>OR</span> <span /></div>

        <button type="button" className="auth-google-button" onClick={() => void handleGoogleSignIn()} disabled={Boolean(action)}>
          {action === 'google' ? <LoaderCircle size={19} className="auth-spinner" /> : <GoogleMark />}
          {action === 'google' ? 'Connecting to Google…' : 'Continue with Google'}
        </button>

        <p className="auth-switch">
          {mode === 'login' ? "Don't have an account?" : 'Already have an account?'}{' '}
          <button type="button" onClick={toggleMode} disabled={Boolean(action)}>
            {mode === 'login' ? 'Sign up' : 'Sign in'}
          </button>
        </p>

        {mode === 'login' && demoCredentials && (
          <button
            type="button"
            className="auth-demo-button"
            onClick={() => void handleDemoLogin()}
            disabled={Boolean(action) || !firebaseReady}
          >
            {action === 'demo' ? <LoaderCircle size={17} className="auth-spinner" /> : null}
            {action === 'demo' ? 'Opening demo workspace…' : 'Explore demo workspace'}
          </button>
        )}

        <div className="auth-security-footnote"><LockKeyhole size={14} /> Secure, private access to your workspace</div>
      </section>
      <footer className="auth-page-footer">© {currentYear} BrandGuard AI</footer>
    </main>
  );
}
