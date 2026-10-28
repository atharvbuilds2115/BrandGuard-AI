import { getApp, getApps, initializeApp } from 'firebase/app';
import {
  browserLocalPersistence,
  createUserWithEmailAndPassword,
  getAuth,
  onAuthStateChanged,
  setPersistence,
  signInWithEmailAndPassword,
  signOut,
  type User,
} from 'firebase/auth';
import { getFirestore } from 'firebase/firestore';

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

const firebaseApp = firebaseConfigured
  ? getApps().length > 0
    ? getApp()
    : initializeApp(firebaseConfig as {
        apiKey: string;
        authDomain: string;
        projectId: string;
        appId: string;
      })
  : null;

export const auth = firebaseApp ? getAuth(firebaseApp) : null;
export const firestore = firebaseApp ? getFirestore(firebaseApp) : null;

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
