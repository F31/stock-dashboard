"""Auth routes (JWT-based login/register)."""
import logging
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
import bcrypt
import jwt
from jwt import ExpiredSignatureError, InvalidTokenError
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from database import get_db
from models import User, OperationLog
from schemas import LoginRequest, TokenResponse
from utils import get_client_ip, get_ip_location

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

SECRET_KEY = "stock-dashboard-secret-key-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7

security = HTTPBearer()


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    to_encode.update({"exp": datetime.now(timezone.utc) + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(token: HTTPAuthorizationCredentials = Depends(security),
                     db: Session = Depends(get_db)):
    credentials_exception = HTTPException(401, "Invalid or expired token")
    try:
        payload = jwt.decode(token.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = int(payload.get("sub"))
        if user_id is None:
            raise credentials_exception
    except ExpiredSignatureError:
        raise credentials_exception
    except InvalidTokenError:
        raise credentials_exception

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception
    return user


def log_action(db: Session, user_id: int, username: str, action: str,
               target: str = "", detail: str = "", ip_address: str = ""):
    entry = OperationLog(
        user_id=user_id, username=username, action=action,
        target=target, detail=detail, ip_address=ip_address,
        ip_location=get_ip_location(ip_address),
    )
    db.add(entry)
    db.commit()


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == req.username).first()
    if not user or not bcrypt.checkpw(req.password.encode(), user.password_hash.encode()):
        raise HTTPException(401, "用户名或密码不正确")
    if getattr(user, "is_active", 1) == 0:
        raise HTTPException(403, "账号已被禁用，请联系管理员")

    token = create_access_token({
        "sub": str(user.id),
        "username": user.username,
        "role": user.role or "user",
    })

    log_action(db, user.id, user.username, "login",
               detail="User login", ip_address=get_client_ip(request))

    return TokenResponse(access_token=token, username=user.username)


@router.post("/register", response_model=TokenResponse)
def register(req: LoginRequest, request: Request, db: Session = Depends(get_db)):
    from models import SystemSetting
    reg_setting = db.query(SystemSetting).filter(SystemSetting.key == "allow_registration").first()
    if reg_setting and reg_setting.value == "0":
        raise HTTPException(403, "注册功能已关闭，请联系管理员")

    existing = db.query(User).filter(User.username == req.username).first()
    if existing:
        raise HTTPException(400, "用户名已存在")

    # First user gets admin role
    user_count = db.query(User).count()
    role = "admin" if user_count == 0 else "user"

    user = User(
        username=req.username,
        password_hash=bcrypt.hashpw(req.password.encode(), bcrypt.gensalt()).decode(),
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token({
        "sub": str(user.id),
        "username": user.username,
        "role": user.role,
    })

    log_action(db, user.id, user.username, "register",
               detail=f"Role: {role}", ip_address=get_client_ip(request))

    return TokenResponse(access_token=token, username=user.username)
