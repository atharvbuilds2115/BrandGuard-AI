import { getApps, initializeApp } from 'firebase/app';
import {
  browserLocalPersistence,
  createUserWithEmailAndPassword,
  getAuth,
  GoogleAuthProvider,
  onAuthStateChanged,
  sendPasswordResetEmail,
  setPersistence,
  signInWithPopup,
  signInWithEmailAndPassword,
  signOut,
  type User,
} from 'firebase/auth';

const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY as string | undefined,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN as string | undefined,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID as string | undefined,
  appId: import.meta.env.VITE_FIREBASE_APP_ID as string | undefined,
};

const configValues = Object.values(firebaseConfig);
const configuredValues = configValues.filter((value) => Boolean(value?.trim())).length;

export const firebaseConfigState =
  configuredValues === 0 ? 'missing' : configuredValues === configValues.length ? 'configured' : 'partial';
export const firebaseConfigured = firebaseConfigState === 'configured';

const demoEmail = import.meta.env.VITE_DEMO_EMAIL?.trim() ?? '';
const demoPassword = import.meta.env.VITE_DEMO_PASSWORD ?? '';

export const demoLoginCredentials =
  demoEmail && demoPassword ? { email: demoEmail, password: demoPassword } : null;

const firebaseApp = firebaseConfigured
  ? getApps().find((app) => app.name === '[DEFAULT]') ??
    initializeApp(firebaseConfig as {
      apiKey: string;
      authDomain: string;
      projectId: string;
      appId: string;
    })
  : null;

export const auth = firebaseApp ? getAuth(firebaseApp) : null;

function requireAuth() {
  if (!auth) throw new Error('Firebase is not configured. Add all VITE_FIREBASE values to .env.local.');
  return auth;
}

export async function registerWithEmail(email: string, password: string): Promise<User> {
  const firebaseAuth = requireAuth();
  await setPersistence(firebaseAuth, browserLocalPersistence);
  const credential = await createUserWithEmailAndPassword(firebaseAuth, email, password);
  return credential.user;
}

export async function loginWithEmail(email: string, password: string): Promise<User> {
  const firebaseAuth = requireAuth();
  await setPersistence(firebaseAuth, browserLocalPersistence);
  const credential = await signInWithEmailAndPassword(firebaseAuth, email, password);
  return credential.user;
}

export async function loginWithGoogle(): Promise<User> {
  const firebaseAuth = requireAuth();
  const provider = new GoogleAuthProvider();
  provider.setCustomParameters({ prompt: 'select_account' });
  const credential = await signInWithPopup(firebaseAuth, provider);
  return credential.user;
}

export async function resetPassword(email: string): Promise<void> {
  await sendPasswordResetEmail(requireAuth(), email);
}

export async function logout(): Promise<void> {
  await signOut(requireAuth());
}

export function listenToAuthState(
  callback: (user: User | null) => void,
  onError: (error: Error) => void,
): () => void {
  return onAuthStateChanged(
    requireAuth(),
    callback,
    (error) => onError(error),
  );
}
