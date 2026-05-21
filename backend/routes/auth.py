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

    from sqlalchemy import text
    try:
        user = db.query(User).filter(User.id == user_id).first()
    except Exception:
        # ORM 列不匹配时降级到原始 SQL
        row = db.execute(
            text("SELECT id, username, role FROM users WHERE id = :id"), {"id": user_id}
        ).fetchone()
        if not row:
            raise credentials_exception
        user = type("U", (), {"id": row[0], "username": row[1], "role": row[2] or "user",
                               "is_active": 1, "password_hash": ""})()
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
    from sqlalchemy import text
    # 用原始 SQL 查询，避免 ORM 在迁移前因 is_active 列不存在而报 500
    row = db.execute(
        text("SELECT id, username, password_hash, role FROM users WHERE username = :u"),
        {"u": req.username},
    ).fetchone()

    if not row or not bcrypt.checkpw(req.password.encode(), row[2].encode()):
        raise HTTPException(401, "用户名或密码不正确")

    # 单独检查 is_active，列不存在时默认视为正常
    try:
        active = db.execute(
            text("SELECT is_active FROM users WHERE id = :id"), {"id": row[0]}
        ).fetchone()
        if active and active[0] == 0:
            raise HTTPException(403, "账号已被禁用，请联系管理员")
    except HTTPException:
        raise
    except Exception:
        pass  # 列不存在（迁移未完成），放行

    token = create_access_token({
        "sub": str(row[0]),
        "username": row[1],
        "role": row[3] or "user",
    })

    log_action(db, row[0], row[1], "login",
               detail="User login", ip_address=get_client_ip(request))

    return TokenResponse(access_token=token, username=row[1])


@router.post("/register", response_model=TokenResponse)
def register(req: LoginRequest, request: Request, db: Session = Depends(get_db)):
    from sqlalchemy import text
    # 检查注册开关，表不存在时默认允许注册
    try:
        from models import SystemSetting
        reg_setting = db.query(SystemSetting).filter(SystemSetting.key == "allow_registration").first()
        if reg_setting and reg_setting.value == "0":
            raise HTTPException(403, "注册功能已关闭，请联系管理员")
    except HTTPException:
        raise
    except Exception:
        pass  # system_settings 表不存在（迁移未完成），默认允许

    existing = db.execute(
        text("SELECT id FROM users WHERE username = :u"), {"u": req.username}
    ).fetchone()
    if existing:
        raise HTTPException(400, "用户名已存在")
    if existing:
        raise HTTPException(400, "用户名已存在")

    from sqlalchemy import text
    # 第一个注册的用户自动成为管理员
    count_row = db.execute(text("SELECT COUNT(*) FROM users")).fetchone()
    role = "admin" if (count_row[0] == 0) else "user"

    pw_hash = bcrypt.hashpw(req.password.encode(), bcrypt.gensalt()).decode()
    user = User(
        username=req.username,
        password_hash=pw_hash,
        role=role,
        is_active=1,
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
