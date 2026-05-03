import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import User, CVRecord, ProfessionalProfile, MatchResult, Assessment
from schemas import ProfessionalProfileRequest, AssessmentSubmitRequest, MatchJobRequest
from auth import get_current_user
from services.matching import calculate_match, get_readiness_level, get_recommendation, infer_seniority
from services.hh_api import get_telegram_dataset
from services.groq_matcher import analyze_cv_job_match, groq_enabled, groq_status

router = APIRouter(prefix="/professional", tags=["Professional"])

ASSESSMENT_QUESTIONS = [
    {"q": "How confident are you with data structures?", "options": ["Beginner", "Familiar", "Proficient", "Expert"]},
    {"q": "Have you built and deployed a production application?", "options": ["No", "Side project only", "Yes, once", "Multiple times"]},
    {"q": "How comfortable are you with SQL?", "options": ["Never used", "Basic queries", "Joins and subqueries", "Advanced optimization"]},
    {"q": "Do you use version control (Git) regularly?", "options": ["No", "Occasionally", "Daily", "Including CI/CD pipelines"]},
    {"q": "How would you rate your problem-solving skills?", "options": ["Developing", "Adequate", "Strong", "Outstanding"]},
]


def _require_professional(current_user: User):
    if current_user.role != "professional":
        raise HTTPException(status_code=403, detail="Professional access only")


def _top_telegram_matches(
    cv_skills: list[str],
    cv_text: str = "",
    profile: ProfessionalProfile | None = None,
    limit: int = 5,
):
    if not cv_skills:
        return []

    profile_years = profile.years_experience if profile and profile.years_experience is not None else None
    profile_level = profile.experience_level if profile else None
    candidate_level = infer_seniority(cv_text, years=profile_years, fallback=profile_level)
    scored_jobs = []
    for job in get_telegram_dataset():
        job_text = " ".join([
            job.get("title", ""),
            job.get("company", ""),
            job.get("area", ""),
            job.get("experience", ""),
            job.get("requirement", ""),
            job.get("responsibility", ""),
            job.get("key_skills", ""),
        ])
        match = calculate_match(cv_skills, job_text, candidate_level=candidate_level, job_level=job.get("experience", ""))
        if match["score"] <= 0 or match.get("required_total", 0) == 0:
            continue
        if match.get("seniority_status") == "too_senior":
            continue
        ranking_score = (
            match["score"]
            + min(len(match["matched"]) * 3, 15)
            + min(match.get("required_total", 0), 10)
            + (8 if match.get("seniority_status") == "aligned" else 0)
        )
        scored_jobs.append({
            **job,
            "match_score": match["score"],
            "base_match_score": match.get("base_score", match["score"]),
            "ranking_score": ranking_score,
            "matched_skills": match["matched"],
            "missing_skills": match["missing"],
            "required_total": match.get("required_total", 0),
            "candidate_level": candidate_level,
            "job_level": match.get("job_level", "unknown"),
            "seniority_status": match.get("seniority_status", "unknown"),
            "recommendation_source": "telegram_all_jobs.csv",
        })

    scored_jobs.sort(
        key=lambda item: (
            item.get("ranking_score", 0),
            item.get("match_score", 0),
            len(item.get("matched_skills", [])),
            item.get("published", ""),
        ),
        reverse=True,
    )

    if groq_enabled():
        refined_jobs = []
        for job in scored_jobs[: min(20, len(scored_jobs))]:
            job_text = " ".join([
                job.get("title", ""),
                job.get("company", ""),
                job.get("area", ""),
                job.get("experience", ""),
                job.get("requirement", ""),
                job.get("responsibility", ""),
                job.get("key_skills", ""),
            ])
            heuristic = {
                "score": job.get("match_score", 0),
                "matched": job.get("matched_skills", []),
                "missing": job.get("missing_skills", []),
                "candidate_level": job.get("candidate_level", "unknown"),
                "job_level": job.get("job_level", "unknown"),
                "seniority_status": job.get("seniority_status", "unknown"),
            }
            ai_match = analyze_cv_job_match(cv_text, job_text, cv_skills, heuristic)
            if not ai_match:
                continue
            if ai_match.get("seniority_status") == "too_senior":
                continue
            job["match_score"] = ai_match["match_score"]
            job["ranking_score"] = ai_match["match_score"] + min(len(ai_match.get("matched_skills", [])) * 3, 15)
            job["matched_skills"] = ai_match.get("matched_skills", job["matched_skills"])
            job["missing_skills"] = ai_match.get("missing_skills", job["missing_skills"])[:8]
            job["candidate_level"] = ai_match.get("candidate_level", job["candidate_level"])
            job["job_level"] = ai_match.get("job_level", job["job_level"])
            job["seniority_status"] = ai_match.get("seniority_status", job["seniority_status"])
            job["project_fit"] = ai_match.get("project_fit", "unknown")
            job["ai_reason"] = ai_match.get("reason", "")
            job["match_engine"] = "groq"
            job["recommendation_source"] = "Groq CV/job analysis"
            refined_jobs.append(job)
        refined_jobs.sort(
            key=lambda item: (
                item.get("ranking_score", 0),
                item.get("match_score", 0),
                len(item.get("matched_skills", [])),
                item.get("published", ""),
            ),
            reverse=True,
        )
        if refined_jobs:
            return refined_jobs[:limit]

        return scored_jobs[:limit]

    return scored_jobs[:limit]


@router.get("/dashboard")
def professional_dashboard(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_professional(current_user)

    cv_records = db.query(CVRecord).filter(CVRecord.user_id == current_user.id).order_by(CVRecord.created_at.desc()).all()
    match_results = db.query(MatchResult).filter(MatchResult.user_id == current_user.id).order_by(MatchResult.created_at.desc()).all()
    profile = db.query(ProfessionalProfile).filter(ProfessionalProfile.user_id == current_user.id).first()
    latest_assessment = db.query(Assessment).filter(Assessment.user_id == current_user.id).order_by(Assessment.created_at.desc()).first()

    all_skills = []
    for r in cv_records:
        if r.extracted_skills:
            all_skills.extend(json.loads(r.extracted_skills))
    unique_skills = list(set(all_skills))

    latest_match_score = 0.0
    if match_results:
        scores = [m.match_score for m in match_results if m.match_score is not None]
        if scores:
            latest_match_score = scores[0]

    missing_skills = []
    if match_results and match_results[0].missing_skills:
        try:
            missing_skills = json.loads(match_results[0].missing_skills)
        except Exception:
            pass

    latest_cv_skills = []
    if cv_records and cv_records[0].extracted_skills:
        try:
            latest_cv_skills = json.loads(cv_records[0].extracted_skills)
        except Exception:
            latest_cv_skills = []

    latest_cv_text = cv_records[0].raw_text if cv_records else ""
    cv_seniority = infer_seniority(
        latest_cv_text,
        years=profile.years_experience if profile and profile.years_experience is not None else None,
        fallback=profile.experience_level if profile else None,
    )

    top_matched_jobs = _top_telegram_matches(latest_cv_skills, latest_cv_text, profile, limit=5)
    if top_matched_jobs:
        latest_match_score = top_matched_jobs[0]["match_score"]

    match_history = []
    for m in match_results[:5]:
        matched = []
        missing = []
        try:
            matched = json.loads(m.matched_skills) if m.matched_skills else []
        except Exception:
            pass
        try:
            missing = json.loads(m.missing_skills) if m.missing_skills else []
        except Exception:
            pass
        match_history.append({
            "id": m.id,
            "job_title": m.job_query or "Job match",
            "match_score": m.match_score or 0,
            "matched_skills": matched[:8],
            "missing_skills": missing[:8],
            "created_at": m.created_at.isoformat(),
        })

    return {
        "user": {"id": current_user.id, "name": current_user.name, "email": current_user.email, "role": current_user.role},
        "profile": {
            "current_position": profile.current_position if profile else None,
            "experience_level": profile.experience_level if profile else None,
            "years_experience": profile.years_experience if profile else None,
            "target_role": profile.target_role if profile else None,
        },
        "latest_match_score": latest_match_score,
        "cv_count": len(cv_records),
        "skills_count": len(unique_skills),
        "skills": unique_skills,
        "missing_skills": missing_skills[:6],
        "searches_done": len(match_results),
        "assessment_score": latest_assessment.score if latest_assessment else None,
        "readiness_level": latest_assessment.readiness_level if latest_assessment else None,
        "cv_seniority": cv_seniority,
        "groq_status": groq_status(),
        "top_matched_jobs": top_matched_jobs,
        "match_history": match_history,
        "last_cv": {
            "filename": cv_records[0].filename,
            "skills": latest_cv_skills,
            "uploaded_at": cv_records[0].created_at.isoformat(),
            "record_id": cv_records[0].id,
        } if cv_records else None,
    }


@router.post("/profile")
def update_profile(req: ProfessionalProfileRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_professional(current_user)
    profile = db.query(ProfessionalProfile).filter(ProfessionalProfile.user_id == current_user.id).first()

    if profile:
        for field, val in req.dict(exclude_none=True).items():
            setattr(profile, field, val)
    else:
        profile = ProfessionalProfile(user_id=current_user.id, **req.dict(exclude_none=True))
        db.add(profile)

    db.commit()
    return {"success": True, "message": "Profile updated"}


@router.post("/match")
def match_cv_to_job(req: MatchJobRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_professional(current_user)

    latest_cv = db.query(CVRecord).filter(CVRecord.user_id == current_user.id).order_by(CVRecord.created_at.desc()).first()
    if not latest_cv:
        raise HTTPException(status_code=400, detail="No CV uploaded yet. Please upload your CV first.")

    cv_skills = json.loads(latest_cv.extracted_skills) if latest_cv.extracted_skills else []
    profile = db.query(ProfessionalProfile).filter(ProfessionalProfile.user_id == current_user.id).first()
    candidate_level = infer_seniority(
        latest_cv.raw_text,
        years=profile.years_experience if profile and profile.years_experience is not None else None,
        fallback=profile.experience_level if profile else None,
    )
    job_text_for_match = " ".join([req.job_title or "", req.job_description])
    result = calculate_match(cv_skills, job_text_for_match, candidate_level=candidate_level)
    ai_match = analyze_cv_job_match(latest_cv.raw_text, job_text_for_match, cv_skills, result)
    if ai_match:
        result["score"] = ai_match["match_score"]
        result["matched"] = ai_match.get("matched_skills", result["matched"])
        result["missing"] = ai_match.get("missing_skills", result["missing"])[:8]
        result["candidate_level"] = ai_match.get("candidate_level", result["candidate_level"])
        result["job_level"] = ai_match.get("job_level", result["job_level"])
        result["seniority_status"] = ai_match.get("seniority_status", result["seniority_status"])
        result["project_fit"] = ai_match.get("project_fit", "unknown")
        result["ai_reason"] = ai_match.get("reason", "")
        result["match_engine"] = "groq"
    elif groq_enabled():
        result["match_engine"] = "heuristic"
        result["ai_warning"] = "Groq analysis is unavailable. Showing fallback skills match."
    recommendation = get_recommendation(result["score"], result["missing"])

    match_record = MatchResult(
        user_id=current_user.id,
        cv_record_id=latest_cv.id,
        job_query=req.job_title or "manual match",
        match_score=result["score"],
        matched_skills=json.dumps(result["matched"]),
        missing_skills=json.dumps(result["missing"]),
        results_json=json.dumps(result),
    )
    db.add(match_record)
    db.commit()

    return {
        "match_score": result["score"],
        "readiness_level": get_readiness_level(result["score"]),
        "matched_skills": result["matched"],
        "missing_skills": result["missing"],
        "candidate_level": result["candidate_level"],
        "job_level": result["job_level"],
        "seniority_status": result["seniority_status"],
        "project_fit": result.get("project_fit"),
        "ai_reason": result.get("ai_reason"),
        "ai_warning": result.get("ai_warning"),
        "match_engine": result.get("match_engine", "heuristic"),
        "recommendation": recommendation,
        "cv_filename": latest_cv.filename,
    }


@router.get("/assessment/questions")
def get_questions(current_user: User = Depends(get_current_user)):
    _require_professional(current_user)
    return {"questions": ASSESSMENT_QUESTIONS, "total": len(ASSESSMENT_QUESTIONS)}


@router.post("/assessment")
def submit_assessment(req: AssessmentSubmitRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_professional(current_user)

    if len(req.answers) != len(ASSESSMENT_QUESTIONS):
        raise HTTPException(status_code=400, detail=f"Expected {len(ASSESSMENT_QUESTIONS)} answers")

    max_score = len(ASSESSMENT_QUESTIONS) * 3
    raw = sum(min(max(a, 0), 3) for a in req.answers)
    score = round(raw / max_score * 100, 1)
    level = get_readiness_level(score)

    if score >= 80:
        feedback = "Strong technical profile. You are well-prepared for senior-level positions."
    elif score >= 60:
        feedback = "Good foundation. Focus on practical projects to reach the next level."
    else:
        feedback = "Keep learning. Build hands-on projects and strengthen your fundamentals."

    record = Assessment(
        user_id=current_user.id,
        role_type="professional",
        test_title=req.test_title,
        score=score,
        readiness_level=level,
        feedback=feedback,
    )
    db.add(record)
    db.commit()

    return {"score": score, "readiness_level": level, "feedback": feedback}
