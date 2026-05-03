import csv
import json
import os
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import User, CVRecord, EmployerProfile, Job, MatchResult, Assessment
from schemas import EmployerProfileRequest, JobCreateRequest
from auth import get_current_user
from services.matching import calculate_match, get_readiness_level
from services.skill_extractor import extract_skills_from_text

router = APIRouter(prefix="/employer", tags=["Employer"])


def _require_employer(current_user: User):
    if current_user.role != "employer":
        raise HTTPException(status_code=403, detail="Employer access only")


@router.get("/dashboard")
def employer_dashboard(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_employer(current_user)

    profile = db.query(EmployerProfile).filter(EmployerProfile.user_id == current_user.id).first()
    jobs = db.query(Job).filter(Job.employer_id == current_user.id).order_by(Job.created_at.desc()).all()
    match_results = db.query(MatchResult).filter(MatchResult.user_id == current_user.id).all()

    avg_score = 0.0
    if match_results:
        scores = [m.match_score for m in match_results if m.match_score is not None]
        avg_score = round(sum(scores) / len(scores), 1) if scores else 0.0

    candidates_with_cvs = (
        db.query(User)
        .filter(User.role != "employer")
        .join(CVRecord, CVRecord.user_id == User.id)
        .distinct()
        .all()
    )

    latest_jobs = [
        {
            "id": j.id,
            "title": j.title,
            "company": j.company,
            "location": j.location,
            "salary": j.salary,
            "created_at": j.created_at.isoformat(),
        }
        for j in jobs[:5]
    ]

    top_candidates = []
    for candidate in candidates_with_cvs[:5]:
        cv_records = db.query(CVRecord).filter(CVRecord.user_id == candidate.id).all()
        all_skills = []
        for r in cv_records:
            if r.extracted_skills:
                all_skills.extend(json.loads(r.extracted_skills))
        unique_skills = list(set(all_skills))
        latest_assessment = (
            db.query(Assessment)
            .filter(Assessment.user_id == candidate.id)
            .order_by(Assessment.created_at.desc())
            .first()
        )
        top_candidates.append({
            "name": candidate.name,
            "role": candidate.role,
            "skills_count": len(unique_skills),
            "readiness_level": latest_assessment.readiness_level if latest_assessment else "not assessed",
        })

    telegram_jobs_count = 0
    try:
        from models import TelegramJob
        telegram_jobs_count = db.query(TelegramJob).count()
    except Exception:
        pass
    if telegram_jobs_count == 0:
        csv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "telegram_all_posts.csv")
        if os.path.exists(csv_path):
            with open(csv_path, "r", encoding="utf-8", newline="") as file:
                telegram_jobs_count = sum(1 for _ in csv.DictReader(file))

    return {
        "user": {
            "id": current_user.id,
            "name": current_user.name,
            "email": current_user.email,
            "role": current_user.role,
        },
        "profile": {
            "company_name": profile.company_name if profile else None,
            "industry": profile.industry if profile else None,
            "recruiter_position": profile.recruiter_position if profile else None,
        },
        "jobs_posted": len(jobs),
        "candidates_reviewed": len(match_results),
        "avg_match_score": avg_score,
        "total_candidates": len(candidates_with_cvs),
        "telegram_jobs_count": telegram_jobs_count,
        "latest_jobs": latest_jobs,
        "top_candidates": top_candidates,
    }


@router.post("/profile")
def update_profile(
    req: EmployerProfileRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_employer(current_user)
    profile = db.query(EmployerProfile).filter(EmployerProfile.user_id == current_user.id).first()

    if profile:
        for field, val in req.dict(exclude_none=True).items():
            setattr(profile, field, val)
    else:
        profile = EmployerProfile(user_id=current_user.id, **req.dict(exclude_none=True))
        db.add(profile)

    db.commit()
    return {"success": True, "message": "Profile updated"}


@router.post("/jobs")
def create_job(
    req: JobCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_employer(current_user)

    job = Job(
        employer_id=current_user.id,
        title=req.title,
        company=req.company,
        description=req.description,
        required_skills=req.required_skills,
        location=req.location,
        salary=req.salary,
        source="internal",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    return {
        "success": True,
        "job_id": job.id,
        "title": job.title,
        "message": "Job posting created successfully",
    }


@router.get("/jobs")
def get_employer_jobs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_employer(current_user)

    jobs = (
        db.query(Job)
        .filter(Job.employer_id == current_user.id)
        .order_by(Job.created_at.desc())
        .all()
    )
    return [
        {
            "id": j.id,
            "title": j.title,
            "company": j.company,
            "location": j.location,
            "salary": j.salary,
            "required_skills": j.required_skills,
            "description": j.description,
            "created_at": j.created_at.isoformat(),
        }
        for j in jobs
    ]


@router.put("/jobs/{job_id}")
def update_job(
    job_id: int,
    req: JobCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_employer(current_user)

    job = db.query(Job).filter(Job.id == job_id, Job.employer_id == current_user.id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or not owned by you")

    job.title = req.title
    job.company = req.company
    job.description = req.description
    job.required_skills = req.required_skills
    job.location = req.location
    job.salary = req.salary

    db.commit()
    db.refresh(job)

    return {
        "success": True,
        "job": {
            "id": job.id,
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "salary": job.salary,
            "required_skills": job.required_skills,
            "description": job.description,
            "created_at": job.created_at.isoformat(),
        },
    }


@router.delete("/jobs/{job_id}")
def delete_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_employer(current_user)

    job = db.query(Job).filter(Job.id == job_id, Job.employer_id == current_user.id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or not owned by you")

    db.query(MatchResult).filter(MatchResult.job_id == job.id, MatchResult.user_id == current_user.id).delete()
    db.delete(job)
    db.commit()

    return {"success": True, "message": "Job deleted"}


@router.get("/candidates")
def get_candidates(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_employer(current_user)

    candidates = (
        db.query(User)
        .filter(User.role.in_(["student", "professional"]))
        .all()
    )

    result = []
    for candidate in candidates:
        cv_records = (
            db.query(CVRecord)
            .filter(CVRecord.user_id == candidate.id)
            .order_by(CVRecord.created_at.desc())
            .all()
        )
        if not cv_records:
            continue

        all_skills = []
        for r in cv_records:
            if r.extracted_skills:
                all_skills.extend(json.loads(r.extracted_skills))
        unique_skills = list(set(all_skills))

        latest_assessment = (
            db.query(Assessment)
            .filter(Assessment.user_id == candidate.id)
            .order_by(Assessment.created_at.desc())
            .first()
        )

        result.append({
            "candidate_id": candidate.id,
            "name": candidate.name,
            "email": candidate.email,
            "role": candidate.role,
            "skills": unique_skills,
            "skills_count": len(unique_skills),
            "cv_count": len(cv_records),
            "assessment_score": latest_assessment.score if latest_assessment else None,
            "readiness_level": latest_assessment.readiness_level if latest_assessment else "not assessed",
            "last_cv_uploaded": cv_records[0].created_at.isoformat() if cv_records else None,
        })

    return result


@router.post("/jobs/{job_id}/match-candidates")
def match_candidates_to_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_employer(current_user)

    job = db.query(Job).filter(Job.id == job_id, Job.employer_id == current_user.id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or not owned by you")

    job_text = f"{job.title} {job.description} {job.required_skills}"

    candidates = db.query(User).filter(User.role.in_(["student", "professional"])).all()

    results = []
    for candidate in candidates:
        cv_records = (
            db.query(CVRecord)
            .filter(CVRecord.user_id == candidate.id)
            .order_by(CVRecord.created_at.desc())
            .all()
        )
        if not cv_records:
            continue

        all_skills = []
        for r in cv_records:
            if r.extracted_skills:
                all_skills.extend(json.loads(r.extracted_skills))
        unique_skills = list(set(all_skills))

        match = calculate_match(unique_skills, job_text, job.required_skills)
        level = get_readiness_level(match["score"])

        match_record = MatchResult(
            user_id=current_user.id,
            job_id=job.id,
            job_query=job.title,
            match_score=match["score"],
            matched_skills=json.dumps(match["matched"]),
            missing_skills=json.dumps(match["missing"]),
            results_json=json.dumps({"candidate_id": candidate.id}),
        )
        db.add(match_record)

        results.append({
            "candidate_id": candidate.id,
            "name": candidate.name,
            "role": candidate.role,
            "skills": unique_skills,
            "match_score": match["score"],
            "matched_skills": match["matched"],
            "missing_skills": match["missing"],
            "required_skills": match["required_skills"],
            "readiness_level": level,
        })

    db.commit()
    results.sort(key=lambda x: x["match_score"], reverse=True)
    return {
        "job_title": job.title,
        "total_candidates": len(results),
        "candidates": results,
    }


@router.post("/match-candidates")
def match_candidates_by_query(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return match_candidates_to_job(job_id, db, current_user)
