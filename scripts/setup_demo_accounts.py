from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import firebase_admin
from dotenv import load_dotenv
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials

from backend.database import Base, engine, init_db
from backend.models import CompanyWorkspace, WorkspaceMembership
from backend.services.workspace_service import DEMO_WORKSPACE_IDS, DEMO_WORKSPACE_NAMES
from sqlalchemy.orm import Session

load_dotenv(PROJECT_ROOT / "backend" / ".env")

ROLES = (
    ("creator", "DEMO_CREATOR_EMAIL", "DEMO_CREATOR_PASSWORD", "Creator Demo"),
    ("reviewer", "DEMO_REVIEWER_EMAIL", "DEMO_REVIEWER_PASSWORD", "Reviewer Demo"),
    ("agency_partner", "DEMO_AGENCY_EMAIL", "DEMO_AGENCY_PASSWORD", "Agency Partner Demo"),
    ("brand_admin", "DEMO_ADMIN_EMAIL", "DEMO_ADMIN_PASSWORD", "Brand Admin Demo"),
)


def initialize_firebase_app():
    project_id = os.getenv("FIREBASE_PROJECT_ID", "").strip()
    service_account_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH", "").strip()
    if not project_id:
        raise RuntimeError("Set FIREBASE_PROJECT_ID in backend/.env")
    if not service_account_path:
        raise RuntimeError("Set FIREBASE_SERVICE_ACCOUNT_PATH in backend/.env")
    path = Path(service_account_path).expanduser()
    if not path.is_file():
        raise RuntimeError(f"Firebase service-account file not found: {path}")
    credential = credentials.Certificate(str(path))
    if credential.project_id != project_id:
        raise RuntimeError("Firebase credential project_id does not match FIREBASE_PROJECT_ID")
    try:
        return firebase_admin.get_app()
    except ValueError:
        return firebase_admin.initialize_app(credential, options={"projectId": project_id})


def main() -> None:
    configured_emails = [
        os.getenv(email_env, "").strip().casefold()
        for _role, email_env, _password_env, _display_name in ROLES
    ]
    if any(not email for email in configured_emails):
        missing = [
            email_env
            for _role, email_env, _password_env, _display_name in ROLES
            if not os.getenv(email_env, "").strip()
        ]
        raise RuntimeError(f"Set all four demo account emails: {', '.join(missing)}")
    if len(set(configured_emails)) != len(ROLES):
        raise RuntimeError("Each demo role must use a distinct Firebase email address.")

    app = initialize_firebase_app()
    init_db()

    print("Demo account setup")
    print("==================")
    with Session(engine) as db:
        Base.metadata.create_all(bind=engine)
        for role, email_env, password_env, display_name in ROLES:
            email = os.getenv(email_env, "").strip()
            if not email:
                raise RuntimeError(f"Set {email_env} in backend/.env")
            try:
                existing_user = firebase_auth.get_user_by_email(email, app=app)
            except firebase_auth.UserNotFoundError:
                existing_user = None
            if existing_user and not (
                existing_user.custom_claims
                and existing_user.custom_claims.get("brandguard_demo") is True
            ):
                raise RuntimeError(
                    f"Refusing to repurpose the existing non-demo Firebase account for {email_env}."
                )
            password = os.getenv(password_env, "").strip()
            generated_password = False
            if not password:
                password = secrets.token_urlsafe(18)
                generated_password = True

            try:
                user = firebase_auth.get_user_by_email(email, app=app)
                firebase_auth.update_user(
                    user.uid,
                    email=email,
                    display_name=display_name,
                    password=password,
                    disabled=False,
                    app=app,
                )
            except firebase_auth.UserNotFoundError:
                user = firebase_auth.create_user(
                    email=email,
                    password=password,
                    display_name=display_name,
                    email_verified=True,
                    disabled=False,
                    app=app,
                )

            firebase_auth.set_custom_user_claims(
                user.uid,
                {
                    "brandguard_demo": True,
                    "demo_role": role,
                    "app_role": role,
                },
                app=app,
            )

            workspace_id = DEMO_WORKSPACE_IDS[role]
            workspace = db.get(CompanyWorkspace, workspace_id)
            if workspace is None:
                db.add(CompanyWorkspace(
                    id=workspace_id,
                    name=DEMO_WORKSPACE_NAMES[role],
                ))
            db.query(WorkspaceMembership).filter(
                WorkspaceMembership.user_id == user.uid,
                WorkspaceMembership.workspace_id.in_(
                    [
                        other_id
                        for other_id in DEMO_WORKSPACE_IDS.values()
                        if other_id != workspace_id
                    ]
                ),
            ).delete(synchronize_session=False)
            membership = db.get(WorkspaceMembership, (workspace_id, user.uid))
            if membership is None:
                db.add(WorkspaceMembership(
                    workspace_id=workspace_id,
                    user_id=user.uid,
                    role="owner" if role == "brand_admin" else "member",
                    app_role=role,
                ))
            else:
                membership.role = "owner" if role == "brand_admin" else "member"
                membership.app_role = role

            print(f"{display_name}: {email}")
            if generated_password:
                print(f"  generated password: {password}")
                print(f"  set {password_env}={password}")
            else:
                print("  password: configured by deployment environment")

        db.commit()

    print("\nAccounts, trusted role claims, and role-specific demo workspaces are ready.")


if __name__ == "__main__":
    main()
