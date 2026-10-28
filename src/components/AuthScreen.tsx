import { useState, type FormEvent } from 'react';
import { AlertCircle, ShieldCheck } from 'lucide-react';
import { createProfile } from '../lib/firestore';
import { loginWithEmail, registerWithEmail } from '../lib/firebase';

type AuthScreenProps = {
  firebaseConfigState: 'missing' | 'partial' | 'configured';
  onTryDemo: () => void;
};

function friendlyAuthError(error: unknown): string {
  const code =
    typeof error === 'object' && error !== null && 'code' in error
      ? String(error.code)
      : '';
  const messages: Record<string, string> = {
    'auth/email-already-in-use': 'An account already exists for this email. Try signing in instead.',
    'auth/invalid-email': 'Enter a valid email address.',
    'auth/invalid-credential': 'The email or password is incorrect.',
    'auth/user-disabled': 'This account has been disabled. Contact your administrator.',
    'auth/too-many-requests': 'Too many attempts. Wait a little and try again.',
    'auth/weak-password': 'Choose a stronger password with at least 8 characters.',
    'auth/operation-not-allowed': 'Email/password sign-in is disabled. Enable it in Firebase Authentication sign-in providers.',
    'auth/network-request-failed': 'Network request failed. Check your connection and try again.',
    'permission-denied': 'Firestore denied access. Check that the deployed rules allow this signed-in user.',
  };
  return messages[code] ?? (error instanceof Error ? error.message : 'Authentication failed. Please try again.');
}

export default function AuthScreen({ firebaseConfigState, onTryDemo }: AuthScreenProps) {
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const firebaseReady = firebaseConfigState === 'configured';

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError('');
    if (!firebaseReady) {
      setError('Configure Firebase before signing in or creating an account.');
      return;
    }
    if (mode === 'register' && password !== confirmPassword) {
      setError('The passwords do not match.');
      return;
    }

    setSubmitting(true);
    try {
      if (mode === 'register') {
        const user = await registerWithEmail(email.trim(), password);
        try {
          await createProfile(user);
        } catch (profileError) {
          await user.delete();
          throw profileError;
        }
      } else {
        await loginWithEmail(email.trim(), password);
      }
    } catch (submitError) {
      setError(friendlyAuthError(submitError));
      setSubmitting(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-100 p-4">
      <section className="w-full max-w-md rounded-3xl border border-slate-200 bg-white p-6 shadow-xl sm:p-8">
        <div className="mb-7 flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-blue-600 text-white">
            <ShieldCheck size={20} />
          </div>
          <div>
            <h1 className="text-xl font-semibold text-slate-900">BrandGuard AI</h1>
            <p className="text-sm text-slate-500">Your AI Brand Safety Copilot</p>
          </div>
        </div>

        <h2 className="text-2xl font-semibold text-slate-900">
          {mode === 'login' ? 'Welcome back' : 'Create your account'}
        </h2>
        <p className="mt-1 text-sm text-slate-500">
          {mode === 'login' ? 'Sign in to your secure workspace.' : 'Register with email and a secure password.'}
        </p>

        <div className="mt-5">
          <button
            type="button"
            onClick={onTryDemo}
            className="inline-flex w-full items-center justify-center gap-2 rounded-xl border border-blue-200 bg-blue-50 px-4 py-2.5 text-sm font-semibold text-blue-700 transition hover:bg-blue-100"
          >
            <ShieldCheck size={16} />
            Try Demo
          </button>
          <div className="mt-5 flex items-center gap-3 text-xs text-slate-400">
            <span className="h-px flex-1 bg-slate-200" />
            <span>OR SIGN IN</span>
            <span className="h-px flex-1 bg-slate-200" />
          </div>
        </div>

        {!firebaseReady && (
          <div role="status" className="mt-5 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
            <p className="font-semibold">Firebase setup required</p>
            <p className="mt-1 leading-6">
              Add these values to the project-root <code className="rounded bg-amber-100 px-1">.env.local</code>,
              using your Firebase Console web app settings, then restart Vite:
            </p>
            <ul className="mt-2 list-inside list-disc font-mono text-xs leading-5">
              <li>VITE_FIREBASE_API_KEY</li>
              <li>VITE_FIREBASE_AUTH_DOMAIN</li>
              <li>VITE_FIREBASE_PROJECT_ID</li>
              <li>VITE_FIREBASE_APP_ID</li>
            </ul>
            <p className="mt-2 leading-6">
              Also enable the Email/Password provider in Firebase Console under Authentication sign-in providers.
            </p>
          </div>
        )}

        <form onSubmit={handleSubmit} className="mt-6 space-y-4">
          <div>
            <label htmlFor="auth-email" className="mb-1.5 block text-sm font-medium text-slate-700">Email</label>
            <input id="auth-email" type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm outline-none focus:border-blue-400" />
          </div>
          <div>
            <label htmlFor="auth-password" className="mb-1.5 block text-sm font-medium text-slate-700">Password</label>
            <input id="auth-password" type="password" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} minLength={8} required value={password} onChange={(event) => setPassword(event.target.value)} className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm outline-none focus:border-blue-400" />
            {mode === 'register' && <p className="mt-1 text-xs text-slate-500">Use at least 8 characters.</p>}
          </div>
          {mode === 'register' && (
            <div>
              <label htmlFor="auth-confirm-password" className="mb-1.5 block text-sm font-medium text-slate-700">Confirm password</label>
              <input id="auth-confirm-password" type="password" autoComplete="new-password" minLength={8} required value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm outline-none focus:border-blue-400" />
            </div>
          )}
          {error && (
            <p role="alert" className="flex items-start gap-2 rounded-xl bg-red-50 px-3 py-2.5 text-sm text-red-700">
              <AlertCircle size={16} className="mt-0.5 shrink-0" /> {error}
            </p>
          )}
          <button type="submit" disabled={submitting || !firebaseReady} className="w-full rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60">
            {submitting ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Create account'}
          </button>
        </form>

        <p className="mt-5 text-center text-sm text-slate-600">
          {mode === 'login' ? 'New to BrandGuard?' : 'Already have an account?'}{' '}
          <button type="button" className="font-semibold text-blue-700 hover:text-blue-800" onClick={() => {
            setMode((current) => current === 'login' ? 'register' : 'login');
            setError('');
          }}>
            {mode === 'login' ? 'Create account' : 'Sign in'}
          </button>
        </p>

      </section>
    </main>
  );
}
