"""Admin routes: user management & operation logs."""
import logging
import bcrypt
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from database import get_db
from models import User, OperationLog
from schemas import (
    UserResponse, UserCreate, UserUpdate,
    PaginatedUsers, LogEntry, PaginatedLogs,
)
from routes.auth import get_current_user
from utils import get_client_ip, get_ip_location  # noqa: re-exported for stocks.py

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


# ── Helpers ──

def log_action(
    db: Session,
    user_id: int,
    username: str,
    action: str,
    target: str = "",
    detail: str = "",
    ip_address: str = "",
):
    entry = OperationLog(
        user_id=user_id,
        username=username,
        action=action,
        target=target,
        detail=detail,
        ip_address=ip_address,
        ip_location=get_ip_location(ip_address),
    )
    db.add(entry)
    db.commit()


# ── User Management ──

@router.get("/users", response_model=PaginatedUsers)
def list_users(
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List users with pagination."""
    query = db.query(User)
    total = query.count()
    users = query.order_by(User.id).offset((page - 1) * page_size).limit(page_size).all()
    return PaginatedUsers(
        total=total,
        page=page,
        page_size=page_size,
        items=[UserResponse(
            id=u.id,
            username=u.username,
            role=u.role or "user",
            created_at=u.created_at.strftime("%Y-%m-%d %H:%M") if u.created_at else "",
        ) for u in users],
    )


@router.post("/users", response_model=UserResponse)
def create_user(
    req: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new user."""
    existing = db.query(User).filter(User.username == req.username).first()
    if existing:
        raise HTTPException(400, "Username already exists")

    user = User(
        username=req.username,
        password_hash=bcrypt.hashpw(req.password.encode(), bcrypt.gensalt()).decode(),
        role=req.role or "user",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    log_action(db, current_user.id, current_user.username,
               "create_user", target=str(user.id), detail=f"username={req.username}",
               ip_address=get_client_ip(request))

    return UserResponse(
        id=user.id,
        username=user.username,
        role=user.role or "user",
        created_at=user.created_at.strftime("%Y-%m-%d %H:%M") if user.created_at else "",
    )


@router.put("/users/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    req: UserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update user fields (username, password, role)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")

    if req.username is not None:
        # Check username uniqueness
        dup = db.query(User).filter(User.username == req.username, User.id != user_id).first()
        if dup:
            raise HTTPException(400, "Username already taken")
        user.username = req.username

    if req.password is not None and req.password.strip():
        user.password_hash = bcrypt.hashpw(req.password.encode(), bcrypt.gensalt()).decode()

    if req.role is not None:
        user.role = req.role

    db.commit()
    db.refresh(user)

    log_action(db, current_user.id, current_user.username,
               "update_user", target=str(user_id),
               detail=f"username={user.username}",
               ip_address=get_client_ip(request))

    return UserResponse(
        id=user.id,
        username=user.username,
        role=user.role or "user",
        created_at=user.created_at.strftime("%Y-%m-%d %H:%M") if user.created_at else "",
    )


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a user. Cannot delete yourself."""
    if user_id == current_user.id:
        raise HTTPException(400, "Cannot delete yourself")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")

    username = user.username
    db.delete(user)
    db.commit()

    log_action(db, current_user.id, current_user.username,
               "delete_user", target=str(user_id), detail=f"username={username}",
               ip_address=get_client_ip(request))

    return {"msg": f"User '{username}' deleted"}


# ── Operation Logs ──

@router.get("/logs", response_model=PaginatedLogs)
def list_logs(
    page: int = 1,
    page_size: int = 20,
    action: str = "",
    username: str = "",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List operation logs with pagination and optional filters."""
    query = db.query(OperationLog)

    if action:
        query = query.filter(OperationLog.action == action)
    if username:
        query = query.filter(OperationLog.username.ilike(f"%{username}%"))

    total = query.count()
    logs = (
        query.order_by(desc(OperationLog.id))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return PaginatedLogs(
        total=total,
        page=page,
        page_size=page_size,
        items=[LogEntry(
            id=log.id,
            user_id=log.user_id,
            username=log.username or "",
            action=log.action,
            target=log.target or "",
            detail=log.detail or "",
            ip_address=log.ip_address or "",
            ip_location=getattr(log, "ip_location", "") or "",
            created_at=log.created_at.strftime("%Y-%m-%d %H:%M:%S") if log.created_at else "",
        ) for log in logs],
    )
