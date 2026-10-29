import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.auth import create_access_token, get_current_user, hash_password, verify_password
from app.config import get_settings
from app.db import get_db
from app.emailer import send_email
from app.models import (
    EquitySnapshot,
    League,
    LeagueMember,
    PasswordResetToken,
    Position,
    Trade,
    User,
)
from app.money import to_dollars, to_micros
from app.ratelimit import rate_limit
from app.schemas import (
    ChangePasswordIn,
    DeleteAccountIn,
    ForgotPasswordIn,
    RegisterIn,
    ResetPasswordIn,
    TokenOut,
    UserOut,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id, username=user.username, email=user.email, cash=to_dollars(user.cash_micros)
    )


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@router.post(
    "/register",
    response_model=TokenOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("register", 10, 3600))],
)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    if db.scalar(select(User).where(func.lower(User.username) == body.username.lower())):
        raise HTTPException(status.HTTP_409_CONFLICT, "That username is taken")
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with that email already exists")
    user = User(
        username=body.username,
        email=email,
        password_hash=hash_password(body.password),
        cash_micros=to_micros(get_settings().starting_cash),
    )
    db.add(user)
    db.commit()
    return TokenOut(access_token=create_access_token(user))


@router.post("/login", response_model=TokenOut, dependencies=[Depends(rate_limit("login", 10, 60))])
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    ident = form.username.strip().lower()
    user = db.scalar(
        select(User).where(or_(func.lower(User.username) == ident, User.email == ident))
    )
    if user is None or not verify_password(form.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong username or password")
    return TokenOut(access_token=create_access_token(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user_out(user)


@router.post(
    "/forgot-password",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit("forgot", 5, 900))],
)
async def forgot_password(body: ForgotPasswordIn, db: Session = Depends(get_db)):
    """Always answers the same way so it can't be used to discover who has an account."""
    settings = get_settings()
    user = db.scalar(select(User).where(User.email == body.email.strip().lower()))
    if user is not None:
        token = secrets.token_urlsafe(32)
        db.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=_hash_token(token),
                expires_at=datetime.now(UTC) + timedelta(minutes=settings.password_reset_minutes),
            )
        )
        db.commit()
        link = f"{settings.app_url.rstrip('/')}/reset-password?token={token}"
        await send_email(
            user.email,
            "Reset your Fomoshi password",
            f"Hi {user.username},\n\n"
            f"Use this link to choose a new password. It expires in "
            f"{settings.password_reset_minutes} minutes.\n\n{link}\n\n"
            "If you didn't ask for this, you can ignore this email.\n",
        )
    return {"detail": "If that email has an account, a reset link is on its way."}


@router.post(
    "/reset-password",
    response_model=TokenOut,
    dependencies=[Depends(rate_limit("reset", 10, 900))],
)
def reset_password(body: ResetPasswordIn, db: Session = Depends(get_db)):
    record = db.scalar(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == _hash_token(body.token))
    )
    now = datetime.now(UTC)
    expires = record.expires_at if record else None
    if expires is not None and expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    if record is None or record.used_at is not None or expires <= now:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This reset link is invalid or expired")
    user = db.get(User, record.user_id)
    user.password_hash = hash_password(body.password)
    user.token_version = (user.token_version or 0) + 1  # sign out everywhere
    record.used_at = now
    db.commit()
    return TokenOut(access_token=create_access_token(user))


@router.post("/change-password", response_model=TokenOut)
def change_password(
    body: ChangePasswordIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Your current password is wrong")
    user.password_hash = hash_password(body.new_password)
    user.token_version = (user.token_version or 0) + 1
    db.commit()
    return TokenOut(access_token=create_access_token(user))


@router.post("/delete-account", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    body: DeleteAccountIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That password is wrong")
    owned = db.scalars(select(League.id).where(League.owner_id == user.id)).all()
    if owned:
        db.execute(delete(LeagueMember).where(LeagueMember.league_id.in_(owned)))
        db.execute(delete(League).where(League.id.in_(owned)))
    for model in (LeagueMember, EquitySnapshot, PasswordResetToken, Trade, Position):
        db.execute(delete(model).where(model.user_id == user.id))
    db.delete(user)
    db.commit()
