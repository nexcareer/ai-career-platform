import json
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from database import get_db
from models import User, CVRecord, MatchResult
from auth import get_current_user
from services.skill_extractor import extract_text_from_file, extract_skills_from_text

router = APIRouter(prefix="/cv", tags=["CV"])


@router.post("/upload")
async def upload_cv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not file.filename.lower().endswith((".pdf", ".docx")):
        raise HTTPException(status_code=400, detail="Only PDF and DOCX files are supported")

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="File is empty")

    text = extract_text_from_file(file.filename, content)
    if not text:
        raise HTTPException(
            status_code=422,
            detail="Could not extract text from this CV. Use text-based PDF or DOCX, not scanned image.",
        )

    skills = extract_skills_from_text(text)

    record = CVRecord(
        user_id=current_user.id,
        filename=file.filename,
        raw_text=text[:5000],
        extracted_skills=json.dumps(skills),
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return {
        "success": True,
        "record_id": record.id,
        "filename": file.filename,
        "skills_found": skills,
        "skills_count": len(skills),
        "message": f"Found {len(skills)} skills in your CV",
    }


@router.get("/history")
def cv_history(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    records = (
        db.query(CVRecord)
        .filter(CVRecord.user_id == current_user.id)
        .order_by(CVRecord.created_at.desc())
        .all()
    )
    return [
        {
            "id": r.id,
            "filename": r.filename,
            "skills": json.loads(r.extracted_skills) if r.extracted_skills else [],
            "uploaded_at": r.created_at.isoformat(),
        }
        for r in records
    ]


@router.get("/{record_id}")
def get_cv(record_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    record = db.query(CVRecord).filter(
        CVRecord.id == record_id,
        CVRecord.user_id == current_user.id,
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="CV record not found")

    return {
        "id": record.id,
        "filename": record.filename,
        "skills": json.loads(record.extracted_skills) if record.extracted_skills else [],
        "uploaded_at": record.created_at.isoformat(),
    }


@router.delete("/{record_id}")
def delete_cv(record_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    record = db.query(CVRecord).filter(
        CVRecord.id == record_id,
        CVRecord.user_id == current_user.id,
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="CV not found")

    db.query(MatchResult).filter(MatchResult.cv_record_id == record.id).update(
        {MatchResult.cv_record_id: None},
        synchronize_session=False,
    )
    db.delete(record)
    db.commit()

    return {"message": "CV deleted successfully", "deleted_id": record_id}
