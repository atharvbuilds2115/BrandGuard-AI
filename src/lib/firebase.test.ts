import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  getApps: vi.fn(),
  initializeApp: vi.fn(),
  getAuth: vi.fn(),
  createUserWithEmailAndPassword: vi.fn(),
  signInWithEmailAndPassword: vi.fn(),
  signInWithCustomToken: vi.fn(),
  setPersistence: vi.fn(),
  signInWithPopup: vi.fn(),
  sendPasswordResetEmail: vi.fn(),
  signOut: vi.fn(),
  setGoogleParameters: vi.fn(),
}));

vi.mock('firebase/app', () => ({
  getApps: mocks.getApps,
  initializeApp: mocks.initializeApp,
}));

vi.mock('firebase/auth', () => ({
  browserLocalPersistence: 'browser-local',
  createUserWithEmailAndPassword: mocks.createUserWithEmailAndPassword,
  getAuth: mocks.getAuth,
  GoogleAuthProvider: class {
    setCustomParameters(parameters: Record<string, string>) {
      mocks.setGoogleParameters(parameters);
    }
  },
  onAuthStateChanged: vi.fn(),
  sendPasswordResetEmail: mocks.sendPasswordResetEmail,
  setPersistence: mocks.setPersistence,
  signInWithCustomToken: mocks.signInWithCustomToken,
  signInWithPopup: mocks.signInWithPopup,
  signInWithEmailAndPassword: mocks.signInWithEmailAndPassword,
  signOut: mocks.signOut,
}));

describe('Firebase authentication methods', () => {
  beforeEach(() => {
    vi.resetModules();
    vi.stubEnv('VITE_FIREBASE_API_KEY', 'test-api-key');
    vi.stubEnv('VITE_FIREBASE_AUTH_DOMAIN', 'test.example.test');
    vi.stubEnv('VITE_FIREBASE_PROJECT_ID', 'test-project');
    vi.stubEnv('VITE_FIREBASE_APP_ID', 'test-app');
    mocks.getApps.mockReturnValue([]);
    mocks.initializeApp.mockReturnValue({ name: 'test-app' });
    mocks.getAuth.mockReturnValue({ currentUser: null });
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.clearAllMocks();
  });

  it('creates an email/password account using Firebase Authentication', async () => {
    const user = { uid: 'new-user' };
    mocks.createUserWithEmailAndPassword.mockResolvedValue({ user });
    const firebase = await import('./firebase');

    await expect(firebase.registerWithEmail('new@example.test', 'strong-password'))
      .resolves.toBe(user);

    expect(mocks.setPersistence).toHaveBeenCalledWith(
      expect.anything(),
      'browser-local',
    );
    expect(mocks.createUserWithEmailAndPassword).toHaveBeenCalledWith(
      expect.anything(),
      'new@example.test',
      'strong-password',
    );
  });

  it('signs in with an existing email/password account', async () => {
    const user = { uid: 'existing-user' };
    mocks.signInWithEmailAndPassword.mockResolvedValue({ user });
    const firebase = await import('./firebase');

    await expect(firebase.loginWithEmail('existing@example.test', 'password'))
      .resolves.toBe(user);

    expect(mocks.setPersistence).toHaveBeenCalledWith(
      expect.anything(),
      'browser-local',
    );
    expect(mocks.signInWithEmailAndPassword).toHaveBeenCalledWith(
      expect.anything(),
      'existing@example.test',
      'password',
    );
  });

  it('starts Google OAuth using the existing Firebase provider', async () => {
    const user = { uid: 'google-user' };
    mocks.signInWithPopup.mockResolvedValue({ user });
    const firebase = await import('./firebase');

    await expect(firebase.loginWithGoogle()).resolves.toBe(user);

    expect(mocks.setGoogleParameters).toHaveBeenCalledWith({ prompt: 'select_account' });
    expect(mocks.signInWithPopup).toHaveBeenCalledWith(
      expect.anything(),
      expect.anything(),
    );
    expect(mocks.setPersistence).toHaveBeenCalledWith(
      expect.anything(),
      'browser-local',
    );
  });

  it('signs in using a backend-issued Firebase custom token', async () => {
    const user = { uid: 'demo-user' };
    mocks.signInWithCustomToken.mockResolvedValue({ user });
    const firebase = await import('./firebase');

    await expect(firebase.loginWithCustomToken('backend-token')).resolves.toBe(user);

    expect(mocks.signInWithCustomToken).toHaveBeenCalledWith(
      expect.anything(),
      'backend-token',
    );
    expect(mocks.setPersistence).toHaveBeenCalledWith(
      expect.anything(),
      'browser-local',
    );
  });

  it('sends a Firebase password reset email', async () => {
    mocks.sendPasswordResetEmail.mockResolvedValue(undefined);
    const firebase = await import('./firebase');

    await expect(firebase.resetPassword('existing@example.test')).resolves.toBeUndefined();

    expect(mocks.sendPasswordResetEmail).toHaveBeenCalledWith(
      expect.anything(),
      'existing@example.test',
    );
  });

  it('signs out the current Firebase user', async () => {
    mocks.signOut.mockResolvedValue(undefined);
    const firebase = await import('./firebase');

    await expect(firebase.logout()).resolves.toBeUndefined();

    expect(mocks.signOut).toHaveBeenCalledWith(expect.anything());
  });
});
