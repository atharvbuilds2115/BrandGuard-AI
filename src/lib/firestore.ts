import {
  collection,
  deleteDoc,
  doc,
  getDoc,
  getDocs,
  setDoc,
  writeBatch,
} from 'firebase/firestore';
import type { User } from 'firebase/auth';
import type { ActivityEvent, Approval, AuditResult, BrandGuideline, WorkspaceSettings } from '../types';
import { defaultSettings } from '../data/demoData';
import { firestore } from './firebase';

export interface CloudWorkspaceData {
  guidelines: BrandGuideline[];
  audits: AuditResult[];
  approvals: Approval[];
  activity: ActivityEvent[];
  settings: WorkspaceSettings;
}

function getDatabase() {
  if (!firestore) throw new Error('Firebase Firestore is not configured.');
  return firestore;
}

function userCollection(uid: string, collectionName: string) {
  return collection(getDatabase(), 'users', uid, collectionName);
}

function userDocument(uid: string, collectionName: string, id: string) {
  return doc(getDatabase(), 'users', uid, collectionName, id);
}

function records<T>(snapshot: Awaited<ReturnType<typeof getDocs>>): T[] {
  return snapshot.docs.map((item) => item.data() as T);
}

export async function loadWorkspace(user: User): Promise<CloudWorkspaceData> {
  const db = getDatabase();
  const uid = user.uid;
  const profileReference = doc(db, 'users', uid);
  const profileSnapshot = await getDoc(profileReference);
  const profile = profileSnapshot.exists()
    ? profileSnapshot.data()
    : {
        uid,
        email: user.email ?? '',
        displayName: user.displayName ?? '',
        createdAt: new Date().toISOString(),
        settings: defaultSettings,
      };

  if (!profileSnapshot.exists()) {
    await setDoc(profileReference, profile, { merge: true });
  }

  const [guidelineSnapshot, auditSnapshot, approvalSnapshot, activitySnapshot] =
    await Promise.all([
      getDocs(userCollection(uid, 'guidelines')),
      getDocs(userCollection(uid, 'audits')),
      getDocs(userCollection(uid, 'approvals')),
      getDocs(userCollection(uid, 'activity')),
    ]);

  const audits = await Promise.all(
    auditSnapshot.docs.map(async (auditDocument) => {
      const findingSnapshot = await getDocs(collection(auditDocument.ref, 'findings'));
      const audit = auditDocument.data() as Omit<AuditResult, 'findings'>;
      return {
        ...audit,
        findings: records<AuditResult['findings'][number]>(findingSnapshot),
      } satisfies AuditResult;
    }),
  );

  return {
    guidelines: records<BrandGuideline>(guidelineSnapshot),
    audits: audits.sort((left, right) => right.createdAt.localeCompare(left.createdAt)),
    approvals: records<Approval>(approvalSnapshot).sort((left, right) => right.submittedAt.localeCompare(left.submittedAt)),
    activity: records<ActivityEvent>(activitySnapshot).sort((left, right) => right.timestamp.localeCompare(left.timestamp)),
    settings: (profile.settings as WorkspaceSettings | undefined) ?? defaultSettings,
  };
}

export async function saveGuideline(uid: string, guideline: BrandGuideline): Promise<void> {
  await setDoc(userDocument(uid, 'guidelines', guideline.id), guideline);
}

export async function removeGuideline(uid: string, id: string): Promise<void> {
  await deleteDoc(userDocument(uid, 'guidelines', id));
}

export async function removeAsset(uid: string, id: string): Promise<void> {
  await deleteDoc(userDocument(uid, 'assets', id));
}

export async function saveAudit(uid: string, audit: AuditResult): Promise<void> {
  const db = getDatabase();
  const batch = writeBatch(db);
  const auditReference = userDocument(uid, 'audits', audit.id);
  const { findings, ...auditData } = audit;
  batch.set(auditReference, auditData);
  for (const finding of findings) {
    batch.set(doc(auditReference, 'findings', encodeURIComponent(finding.id)), finding);
  }
  await batch.commit();
}

export async function saveAuditSubmission(uid: string, audit: AuditResult, approval: Approval): Promise<void> {
  const db = getDatabase();
  const batch = writeBatch(db);
  const auditReference = userDocument(uid, 'audits', audit.id);
  const { findings, ...auditData } = audit;
  batch.set(auditReference, auditData);
  for (const finding of findings) {
    batch.set(doc(auditReference, 'findings', encodeURIComponent(finding.id)), finding);
  }
  batch.set(userDocument(uid, 'approvals', approval.id), approval);
  await batch.commit();
}

export async function saveApproval(uid: string, approval: Approval): Promise<void> {
  await setDoc(userDocument(uid, 'approvals', approval.id), approval);
}

export async function saveActivity(uid: string, event: ActivityEvent): Promise<void> {
  await setDoc(userDocument(uid, 'activity', event.id), event);
}

export async function saveSettings(uid: string, user: User, settings: WorkspaceSettings): Promise<void> {
  await setDoc(
    doc(getDatabase(), 'users', uid),
    {
      uid,
      email: user.email ?? '',
      displayName: user.displayName ?? '',
      settings,
    },
    { merge: true },
  );
}

export async function createProfile(user: User): Promise<void> {
  await setDoc(
    doc(getDatabase(), 'users', user.uid),
    {
      uid: user.uid,
      email: user.email ?? '',
      displayName: user.displayName ?? '',
      createdAt: new Date().toISOString(),
      settings: defaultSettings,
    },
    { merge: true },
  );
}

export function cloudErrorMessage(error: unknown): string {
  if (typeof error === 'object' && error !== null && 'code' in error) {
    const code = String(error.code).split('/').pop();
    if (code === 'permission-denied') {
      return 'Firestore denied access to this account. Confirm that the deployed Firestore rules match firestore.rules and allow the signed-in user to access only their own users/{uid} data.';
    }
    if (code === 'not-found' || code === 'failed-precondition') {
      return 'Firestore is unavailable for the configured Firebase project. Confirm that a Firestore database has been created and that VITE_FIREBASE_PROJECT_ID identifies the intended project.';
    }
    if (code === 'unavailable' || code === 'network-request-failed') {
      return 'Firebase could not be reached. Check the network connection and Firebase service availability, then retry.';
    }
    if (code === 'unauthenticated' || code === 'user-token-expired') {
      return 'The Firebase sign-in session is no longer valid. Sign out and sign in again.';
    }
  }
  if (error instanceof Error && error.message) return error.message;
  return 'The cloud data operation failed. Please try again.';
}
