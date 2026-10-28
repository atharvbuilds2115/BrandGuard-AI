# BrandGuard AI 2.0

BrandGuard is a React + TypeScript + Vite workspace with Firebase Authentication and Cloud Firestore support, plus a FastAPI/SQLite service for authenticated asset uploads and the existing audit API.

## Features

- Email/password registration and sign-in using Firebase Authentication
- Persistent Firebase sign-in state with protected application access
- Explicit Try Demo experience with sample dashboards, guidelines, audit history, and findings
- Demo edits remain in memory for the current session and never write to Firebase or the backend
- User-scoped Firestore profiles, guidelines, audit history/findings, approvals, and activity
- Deterministic brand-rule audit checks retained in the frontend and backend
- Private, authenticated uploads through FastAPI (Firebase Cloud Storage is not used)
- SQLite persistence for backend asset metadata and file references

## 1. Install frontend dependencies

From the project root in PowerShell:

```powershell
npm install
```

## 2. Configure Firebase in the Console

Use the Firebase project you already created:

1. In **Project settings → General → Your apps**, select or create a **Web app**. Registering a Web app does not require Storage.
2. Copy the following values from its Firebase configuration object:
   - `apiKey`
   - `authDomain`
   - `projectId`
   - `appId`
3. In **Authentication → Sign-in method** (or **Sign-in providers**), enable **Email/Password**.
4. In **Firestore Database**, create a database in **production mode**.
5. In **Firestore Database → Rules**, publish the contents of [`firestore.rules`](./firestore.rules). The rules only allow an authenticated user to access documents beneath their own `users/{uid}` path.
6. In **Authentication → Settings → Authorized domains**, ensure the host used for development is listed (normally `localhost`).

Do not enable Firebase Storage; the app does not initialize or import it.

## 3. Set up frontend environment

The root `.env.local` is ignored by Git and has empty placeholders. Fill it using the values copied from **Project settings → General → Your apps**:

```dotenv
VITE_FIREBASE_API_KEY=the_web_app_apiKey
VITE_FIREBASE_AUTH_DOMAIN=the_web_app_authDomain
VITE_FIREBASE_PROJECT_ID=the_web_app_projectId
VITE_FIREBASE_APP_ID=the_web_app_appId
VITE_API_BASE_URL=http://localhost:8000
```

These are Firebase web-app configuration values, not service-account credentials. Do not put a private key, password, or service-account JSON in this file. Restart Vite after changing environment values.

The app shows its sign-in and registration screen until all four Firebase values are configured. It does not automatically bypass authentication when Firebase configuration is missing or incomplete; users can explicitly choose **Try Demo** to open an isolated, in-memory sample workspace. Demo changes are temporary and do not write to localStorage, Firestore, or backend APIs. **Exit Demo** returns to the sign-in screen. With configuration present, the regular application still requires Firebase sign-in and preserves the session across refreshes.

## 4. Configure Firebase Admin for the backend

The FastAPI API verifies Firebase ID tokens using Firebase Admin. It does not trust a UID in a request body. Health checks remain public; application API routes require a verified Bearer token.

Create `backend/.env` from the sample if it does not exist:

```powershell
Copy-Item backend\.env.example backend\.env
```

Set at least:

```dotenv
FIREBASE_PROJECT_ID=your-firebase-project-id
FRONTEND_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

Configure Admin credentials using **one** of these methods:

- **Application Default Credentials (preferred when available):** configure ADC for the backend host (for local Google Cloud SDK installations, run `gcloud auth application-default login` using an account authorized for this Firebase project).
- **Service-account file:** in **Project settings → Service accounts**, create a private key only if required. Store the downloaded file outside this repository, restrict access to it, and set `FIREBASE_SERVICE_ACCOUNT_PATH` to its absolute path in `backend/.env`.

Never commit or share the service-account file. `backend/.env`, `.env.local`, virtual environments, and common service-account JSON filenames are excluded by `.gitignore`. If Admin credentials are absent, protected API calls return a setup error instead of disabling verification.

## 5. Start the backend and frontend

In the project-root PowerShell terminal, install backend requirements into the existing virtual environment and start FastAPI:

```powershell
.\backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\backend\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

The backend documentation is at `http://127.0.0.1:8000/docs`; the public health endpoint is `http://127.0.0.1:8000/api/health`.

In a second project-root terminal:

```powershell
npm run dev -- --host 127.0.0.1
```

Open the Vite URL shown in the terminal (normally `http://localhost:5173`).

## Data ownership and persistence

- **Firestore is the frontend workspace source of truth:** `users/{uid}` stores the profile and settings; its `guidelines`, `audits`, `approvals`, and `activity` subcollections store that account's data. Each audit's findings are stored beneath `audits/{auditId}/findings`.
- **Assets and uploaded bytes stay on the backend:** authenticated API requests store metadata in SQLite and the file outside the project directory, by default under `%LOCALAPPDATA%\BrandGuardAI\uploads` on Windows. The directory is not mounted as a public static route. A custom `UPLOAD_DIR` must also resolve outside the project directory. The server validates allowed suffixes/MIME types and size, generates random storage filenames, and checks ownership on list, update, and download operations.
- **The existing SQLite API remains available but separate:** its guideline, audit, finding, approval, activity, and asset endpoints require a Firebase ID token and scope new records to its verified UID. The React workspace writes its guidelines/audits/approvals/activity to Firestore; no implicit synchronization between Firestore and the compatibility SQLite API is performed.
- **Existing SQLite rows are preserved:** startup only adds nullable `user_id` columns/indexes when missing. Existing rows are not deleted or assigned an owner based on guesswork. Legacy rows with no owner are hidden from authenticated per-user API results until an administrator confirms who owns them and explicitly assigns their verified Firebase UID. Back up the database before any manual ownership migration.
- **No automatic localStorage-to-Firestore or SQLite-to-Firestore migration runs.** This avoids copying demo data or assigning potentially shared records to the wrong account.
- The frontend and backend rule-based audit engines remain deterministic; results are not represented as responses from an external AI service.

If the whole legacy SQLite database belongs to one verified user, an administrator can assign its currently unowned rows after taking a backup and verifying that user's UID in Firebase Authentication. Run a transaction against the configured SQLite database:

```sql
BEGIN IMMEDIATE;
UPDATE brand_guidelines SET user_id = 'VERIFIED_FIREBASE_UID' WHERE user_id IS NULL;
UPDATE assets SET user_id = 'VERIFIED_FIREBASE_UID' WHERE user_id IS NULL;
UPDATE audits SET user_id = 'VERIFIED_FIREBASE_UID' WHERE user_id IS NULL;
UPDATE audit_findings SET user_id = 'VERIFIED_FIREBASE_UID' WHERE user_id IS NULL;
UPDATE approvals SET user_id = 'VERIFIED_FIREBASE_UID' WHERE user_id IS NULL;
UPDATE activity_events SET user_id = 'VERIFIED_FIREBASE_UID' WHERE user_id IS NULL;
COMMIT;
```

Do not use this bulk assignment if the legacy database contains data from multiple people. Determine ownership record by record instead.

## Test auth and data access

1. With Firebase web configuration filled and the backend credentials configured, register an account from the sign-in screen.
2. Sign out and sign back in to verify persisted auth state and workspace reload.
3. Add/edit a brand rule, run an audit, inspect/update a finding, and approve/reject it. Verify the documents appear under the signed-in UID in Firestore.
4. Upload an allowed file from the Asset Library. The request goes to FastAPI with the current Firebase ID token; the file and metadata remain in backend-managed storage/SQLite.
5. `GET /api/health` is public. Protected routes such as `GET /api/guidelines` return HTTP 401 without a Bearer token. A supplied token must be verified by Firebase Admin; missing Admin credentials produce HTTP 503 rather than accepting the request.

## Build and checks

```powershell
npm run build
.\backend\.venv\Scripts\python.exe -c "from backend.main import app; print(app.title)"
```

## Troubleshooting

- **Configuration incomplete:** fill all four `VITE_FIREBASE_*` values and restart Vite.
- **`auth/operation-not-allowed`:** enable Email/Password in Firebase Authentication sign-in providers.
- **Firestore `permission-denied`:** publish [`firestore.rules`](./firestore.rules) and ensure the user is signed in to the intended project.
- **Backend 503 for protected operations:** configure `FIREBASE_PROJECT_ID` and either `FIREBASE_SERVICE_ACCOUNT_PATH` or valid ADC for the backend process.
- **Asset Library reports backend unavailable:** start FastAPI and configure Admin credentials; uploads and metadata access intentionally fail closed when token verification is unavailable.
- **CORS errors:** add the exact Vite origin to `FRONTEND_ORIGINS` in `backend/.env`, then restart FastAPI.
- **Upload rejected:** only TXT, CSV, PDF, DOCX, PNG, JPEG, and WEBP are accepted by the current upload service; the default maximum size is 10 MB.
- **Existing SQLite data is not visible:** old rows remain intact but are intentionally inaccessible until their ownership has been verified and assigned as described above.
