"""Analysis reports endpoints — upload files / add links / list / delete."""
import os
import uuid
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from database import get_db
from models import StockReport, User
from routes.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["reports"])

REPORTS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "frontend", "reports"
)
AUTO_REPORTS_DIR = os.path.join(REPORTS_DIR, "auto")
ALLOWED_EXTENSIONS = {".pdf", ".ppt", ".pptx", ".doc", ".docx", ".html", ".htm"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


def _scan_auto_reports(stock_code: str, market: str) -> list:
    """Scan reports/auto/ for files matching this stock.

    Matching rules (in order):
      1. Subdirectory  auto/{stock_code}_{market}/   e.g. auto/688008_A/
      2. Subdirectory  auto/{stock_code}/            e.g. auto/688008/
      3. Files in auto/ root prefixed by {stock_code}_ or {stock_code}.
    """
    if not os.path.isdir(AUTO_REPORTS_DIR):
        return []

    results = []
    seen = set()
    code_lower = stock_code.lower()

    # Rule 1 & 2: subdirectories
    for subdir_name in (f"{stock_code}_{market}", stock_code):
        subdir = os.path.join(AUTO_REPORTS_DIR, subdir_name)
        if not os.path.isdir(subdir):
            continue
        for fname in sorted(os.listdir(subdir)):
            fpath = os.path.join(subdir, fname)
            if not os.path.isfile(fpath):
                continue
            ext = os.path.splitext(fname)[1].lower()
            if ext not in ALLOWED_EXTENSIONS:
                continue
            key = f"{subdir_name}/{fname}"
            if key in seen:
                continue
            seen.add(key)
            mtime = os.path.getmtime(fpath)
            title = os.path.splitext(fname)[0]
            results.append({
                "id": f"auto:{key}",
                "stock_code": stock_code,
                "market": market,
                "title": title,
                "report_type": "auto",
                "file_name": fname,
                "url": f"/reports/auto/{key}",
                "uploader_id": 0,
                "uploader_name": "自动导入",
                "created_at": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M"),
            })
        break  # use the first matched subdirectory only

    # Rule 3: files in auto/ root prefixed with stock_code
    for fname in sorted(os.listdir(AUTO_REPORTS_DIR)):
        fpath = os.path.join(AUTO_REPORTS_DIR, fname)
        if not os.path.isfile(fpath):
            continue
        if fname in seen:
            continue
        ext = os.path.splitext(fname)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            continue
        fl = fname.lower()
        if fl.startswith(code_lower + "_") or fl.startswith(code_lower + "."):
            seen.add(fname)
            mtime = os.path.getmtime(fpath)
            title = os.path.splitext(fname)[0]
            results.append({
                "id": f"auto:{fname}",
                "stock_code": stock_code,
                "market": market,
                "title": title,
                "report_type": "auto",
                "file_name": fname,
                "url": f"/reports/auto/{fname}",
                "uploader_id": 0,
                "uploader_name": "自动导入",
                "created_at": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M"),
            })

    return results


def _report_to_dict(r: StockReport) -> dict:
    return {
        "id": r.id,
        "stock_code": r.stock_code,
        "market": r.market,
        "title": r.title,
        "report_type": r.report_type,
        "file_name": r.file_name,
        "url": r.url,
        "uploader_id": r.uploader_id,
        "uploader_name": r.uploader_name,
        "created_at": r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "",
    }


@router.get("/reports")
def list_reports(
    stock_code: str,
    market: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List analysis reports for a stock: user-uploaded + auto-scanned from reports/auto/."""
    db_reports = (
        db.query(StockReport)
        .filter(StockReport.stock_code == stock_code, StockReport.market == market)
        .order_by(StockReport.created_at.desc())
        .all()
    )
    result = [_report_to_dict(r) for r in db_reports]
    result.extend(_scan_auto_reports(stock_code, market))
    return result


@router.post("/reports/upload")
async def upload_report(
    stock_code: str = Form(...),
    market: str = Form(...),
    title: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Upload a file report (PDF / PPT / Word / HTML)."""
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"不支持的文件类型: {ext}，支持 PDF / PPT / Word / HTML")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(400, "文件超过50MB限制")

    os.makedirs(REPORTS_DIR, exist_ok=True)
    safe_name = f"{uuid.uuid4().hex}{ext}"
    dest = os.path.join(REPORTS_DIR, safe_name)
    with open(dest, "wb") as f:
        f.write(content)

    report = StockReport(
        stock_code=stock_code,
        market=market,
        title=title.strip() or file.filename,
        report_type="file",
        file_name=safe_name,
        url=f"/reports/{safe_name}",
        uploader_id=user.id,
        uploader_name=user.username,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    logger.info(f"Report uploaded: {safe_name} by {user.username} for {stock_code}")
    return _report_to_dict(report)


class LinkReportRequest(BaseModel):
    stock_code: str
    market: str
    title: str
    url: str


@router.post("/reports/link")
def add_link_report(
    req: LinkReportRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Add an external link as a report."""
    if not req.url.startswith(("http://", "https://", "/")):
        raise HTTPException(400, "请输入有效的链接地址")
    if not req.title.strip():
        raise HTTPException(400, "标题不能为空")

    report = StockReport(
        stock_code=req.stock_code,
        market=req.market,
        title=req.title.strip(),
        report_type="link",
        file_name="",
        url=req.url.strip(),
        uploader_id=user.id,
        uploader_name=user.username,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return _report_to_dict(report)


@router.delete("/reports/{report_id}")
def delete_report(
    report_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Delete a report. Admins can delete any; users can only delete their own."""
    report = db.query(StockReport).filter(StockReport.id == report_id).first()
    if not report:
        raise HTTPException(404, "报告不存在")
    if user.role != "admin" and report.uploader_id != user.id:
        raise HTTPException(403, "无权删除此报告")

    # Remove file from disk
    if report.report_type == "file" and report.file_name:
        path = os.path.join(REPORTS_DIR, report.file_name)
        if os.path.exists(path):
            os.remove(path)

    db.delete(report)
    db.commit()
    return {"msg": "已删除"}
