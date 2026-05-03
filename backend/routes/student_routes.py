import json
import os
import re
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from database import get_db
from models import User, CVRecord, StudentProfile, LearningRoadmap
from schemas import StudentProfileRequest
from auth import get_current_user
from services.skill_extractor import (
    extract_text_from_pdf,
    extract_skills_from_text,
    _extract_courses_from_transcript,
    _is_transcript,
    _skills_from_courses,
    COURSE_TO_SKILLS,
)
try:
    from services.student_recommender import StudentProfessionRecommender
except Exception:
    StudentProfessionRecommender = None

router = APIRouter(prefix="/student", tags=["Student"])
_student_recommender = None
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL   = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_URL     = "https://api.groq.com/openai/v1/chat/completions"
SEM_COLOURS = ["#5b7fff", "#00e5c0", "#a259ff", "#ffb347", "#00c9a7", "#ff7eb3", "#f9c74f"]
ROLE_SKILL_MAP: dict[str, list[str]] = {
    "ml engineer":        ["python", "machine learning", "deep learning", "tensorflow", "pytorch", "statistics", "sql", "docker", "mlops"],
    "data scientist":     ["python", "machine learning", "statistics", "probability", "pandas", "numpy", "sql", "data visualization"],
    "data analyst":       ["sql", "python", "statistics", "data analysis", "tableau", "excel", "data visualization", "reporting"],
    "data engineer":      ["python", "sql", "spark", "airflow", "postgresql", "docker", "etl", "database"],
    "backend developer":  ["python", "fastapi", "postgresql", "docker", "rest api", "sql", "linux", "git"],
    "frontend developer": ["javascript", "react", "typescript", "html", "css", "git", "design patterns"],
    "fullstack developer":["javascript", "react", "python", "postgresql", "docker", "html", "css", "git"],
    "devops engineer":    ["docker", "kubernetes", "aws", "linux", "terraform", "ci/cd", "bash", "networking"],
    "mobile developer":   ["swift", "kotlin", "react native", "flutter", "mobile", "git", "rest api"],
    "qa engineer":        ["python", "sql", "testing", "selenium", "postman", "ci/cd"],
    "product manager":    ["project management", "agile", "scrum", "business analysis", "jira", "figma"],
    "security engineer":  ["information security", "networking", "linux", "cybersecurity"],
    "designer":           ["figma", "ux", "ui", "prototyping", "user research", "design systems", "adobe"],
    "graphic designer":   ["figma", "adobe photoshop", "adobe illustrator", "typography", "branding", "layout design"],
}

PROFESSION_META: dict[str, dict] = {
    "ml engineer":        {"emoji": "🤖", "category": "AI/ML",        "color": "#5b7fff"},
    "data scientist":     {"emoji": "🔬", "category": "Data",         "color": "#a259ff"},
    "data analyst":       {"emoji": "📊", "category": "Data",         "color": "#00e5c0"},
    "data engineer":      {"emoji": "🔧", "category": "Data",         "color": "#ffb347"},
    "backend developer":  {"emoji": "⚙️",  "category": "Engineering", "color": "#5b7fff"},
    "frontend developer": {"emoji": "🎨", "category": "Engineering",  "color": "#00e5c0"},
    "fullstack developer":{"emoji": "🖥️",  "category": "Engineering", "color": "#a259ff"},
    "devops engineer":    {"emoji": "🛠️",  "category": "Infrastructure","color": "#ffb347"},
    "mobile developer":   {"emoji": "📱", "category": "Engineering",  "color": "#ff7eb3"},
    "qa engineer":        {"emoji": "✅", "category": "Quality",      "color": "#00c9a7"},
    "product manager":    {"emoji": "🎯", "category": "Management",   "color": "#a259ff"},
    "security engineer":  {"emoji": "🔒", "category": "Security",     "color": "#ff5b5b"},
    "designer":           {"emoji": "✏️", "category": "Design",       "color": "#ff7eb3"},
    "graphic designer":   {"emoji": "🎨", "category": "Design",       "color": "#ff7eb3"},
}

def _require_student(user: User):
    if user.role != "student":
        raise HTTPException(status_code=403, detail="Student access only")


def _get_all_skills(cv_records: list) -> list[str]:
    all_skills = []
    for r in cv_records:
        if r.extracted_skills:
            try:
                all_skills.extend(json.loads(r.extracted_skills))
            except Exception:
                pass
    return sorted(set(s.lower().strip() for s in all_skills))


def _calculate_readiness(skills: list[str], career_goal: str) -> int:
    if not career_goal or not skills:
        return min(len(skills) * 5, 40)

    role_skills = _get_role_skills(career_goal)
    if not role_skills:
        return min(len(skills) * 5, 60)

    skills_lower = [s.lower() for s in skills]
    matched = sum(
        1 for rs in role_skills
        if any(rs in sk or sk in rs for sk in skills_lower)
    )
    return round(matched / len(role_skills) * 100)


def _get_role_skills(goal: str) -> list[str]:
    goal_lower = goal.lower().strip()
    for role, skills in ROLE_SKILL_MAP.items():
        if role in goal_lower or goal_lower in role:
            return skills
    return []


def _get_missing_skills(user_skills: list[str], career_goal: str) -> list[str]:
    if not career_goal:
        return []
    role_skills = _get_role_skills(career_goal)
    if not role_skills:
        return []
    skills_lower = [s.lower() for s in user_skills]
    return [
        rs for rs in role_skills
        if not any(rs in sk or sk in rs for sk in skills_lower)
    ]


def _recommend_roles(skills: list[str]) -> list[dict]:
    skills_lower = [s.lower() for s in skills]
    results = []
    for role, role_skills in ROLE_SKILL_MAP.items():
        matched = sum(
            1 for rs in role_skills
            if any(rs in sk or sk in rs for sk in skills_lower)
        )
        pct = round(matched / len(role_skills) * 100) if role_skills else 0
        meta = PROFESSION_META.get(role, {"emoji": "🎯", "category": "Other", "color": "#7b82a8"})
        results.append({
            "profession":   role,
            "emoji":        meta["emoji"],
            "category":     meta["category"],
            "color":        meta["color"],
            "skill_match":  pct,
            "confidence":   pct,
            "matched_count": matched,
            "total_required": len(role_skills),
        })
    return sorted(results, key=lambda x: x["skill_match"], reverse=True)[:5]


def _get_student_recommender():
    global _student_recommender
    if StudentProfessionRecommender is None:
        return None
    if _student_recommender is None:
        _student_recommender = StudentProfessionRecommender.load()
    return _student_recommender


def _course_titles(courses: list[dict]) -> list[str]:
    return [c.get("title", "") for c in courses if c.get("title")]


def _recommend_roles_for_student(
    skills: list[str],
    courses: list[dict] | None = None,
    career_goal: str = "",
    gpa: Optional[float] = None,
) -> list[dict]:
    if not skills:
        return []

    try:
        rec = _get_student_recommender()
        if rec is None:
            raise RuntimeError("Student recommender is unavailable")
        result = rec.recommend(
            skills=skills,
            courses=_course_titles(courses or []),
            career_goal=career_goal,
            gpa=gpa,
            top_n=5,
        )
        roles = []
        for r in result.get("recommendations", []):
            roles.append({
                "profession":      r.get("profession"),
                "emoji":           r.get("emoji", "🎯"),
                "category":        r.get("category", "Other"),
                "color":           r.get("color", "#7b82a8"),
                "skill_match":     r.get("skill_match", 0),
                "confidence":      r.get("confidence", 0),
                "matched_skills":  r.get("matched_skills", []),
                "missing_skills":  r.get("missing_skills", []),
                "recommendation_source": "telegram_ml",
            })
        return roles or _recommend_roles(skills)
    except Exception as e:
        print(f"[StudentRecommender] fallback: {e}")
        roles = _recommend_roles(skills)
        for r in roles:
            r["recommendation_source"] = "skill_map"
        return roles

async def _call_groq(system_prompt: str, user_prompt: str, max_tokens: int = 900) -> str:
    if not GROQ_API_KEY:
        return ""
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": GROQ_MODEL,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        "temperature": 0.4,
    }
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            resp = await client.post(GROQ_URL, json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"[Groq] error: {e}")
        return ""


async def _groq_insight(name: str, courses: list[dict], skills: list[str]) -> str:
    if not GROQ_API_KEY:
        top = ", ".join(skills[:5]) if skills else "various subjects"
        return (f"Your transcript shows a strong academic record. "
                f"Key skills identified: <strong>{top}</strong>. "
                f"Build practical projects to complement your coursework.")

    sys_prompt = (
        "You are a concise AI career advisor. "
        "Return a single paragraph (3-5 sentences, max 80 words) of personalised career insight. "
        "Use <strong>tags</strong> for key terms. Be specific and actionable. English only."
    )
    course_str = "; ".join(
        f"{c['title']} ({c.get('score', '?')})" for c in courses[:15] if c.get("score")
    )
    user_msg = (
        f"Student: {name}\n"
        f"Courses: {course_str}\n"
        f"Skills: {', '.join(skills[:12])}"
    )
    text = await _call_groq(sys_prompt, user_msg, max_tokens=200)
    return text or f"Your courses show strengths in <strong>{', '.join(skills[:3])}</strong>. Keep building practical projects."


async def _groq_roadmap(skills: list[str], missing: list[str], career_goal: str) -> list[dict]:
    if not GROQ_API_KEY or not missing:
        return _fallback_roadmap(skills, missing, career_goal)

    sys_prompt = (
        "You are a career roadmap generator. "
        "Return ONLY a valid JSON array of objects: "
        '[{"skill":"...","actions":["action1","action2","action3"]}] '
        "Each object is one missing skill with 3 concrete learning actions. "
        "No markdown, no explanation, just JSON array."
    )
    user_msg = (
        f"Student current skills: {', '.join(skills[:10])}\n"
        f"Career goal: {career_goal}\n"
        f"Missing skills to learn (up to 6): {', '.join(missing[:6])}"
    )
    raw = await _call_groq(sys_prompt, user_msg, max_tokens=800)
    try:
        clean = re.sub(r"```(?:json)?|```", "", raw).strip()
        steps = json.loads(clean)
        if isinstance(steps, list) and steps and "skill" in steps[0]:
            return steps[:6]
    except Exception:
        pass
    return _fallback_roadmap(skills, missing, career_goal)


def _fallback_roadmap(skills: list[str], missing: list[str], career_goal: str) -> list[dict]:
    result = []
    for skill in missing[:6]:
        result.append({
            "skill": skill,
            "actions": [
                f"Learn {skill} fundamentals via Coursera or edX",
                f"Build a hands-on project using {skill}",
                f"Add {skill} to your GitHub portfolio",
            ]
        })
    if not result:
        result = [
            {"skill": career_goal or "target role", "actions": [
                "Define your target role clearly",
                "Upload your transcript to extract skills",
                "Set a career goal in your profile",
            ]}
        ]
    return result

def _assign_semesters(raw_text: str, courses: list[dict]) -> tuple[list[dict], list[dict]]:
    heading_pattern = re.compile(r'(\d{4})\s*[-–]\s*(\d{4})[.\s]+([12])', re.IGNORECASE)
    headings = []
    for m in heading_pattern.finditer(raw_text.upper()):
        y1, y2, sem = m.group(1), m.group(2), m.group(3)
        key  = f"{y1[-2:]}{y2[-2:]}-{sem}"
        name = f"{y1}–{y2} Sem {sem}"
        headings.append((m.start(), key, name))

    if not headings:
        for c in courses:
            c["sem"] = "sem-1"
        return courses, [{
            "key": "sem-1", "name": "Transcript", "gpa": None, "avg": None,
            "credits": sum(c.get("credits", 3) for c in courses),
            "courses": len(courses), "color": SEM_COLOURS[0], "current": False,
        }]

    text_upper = raw_text.upper()
    semester_slices = []
    for i, (pos, key, name) in enumerate(headings):
        end = headings[i+1][0] if i+1 < len(headings) else len(text_upper)
        semester_slices.append((key, name, text_upper[pos:end]))

    assigned = {c["code"]: None for c in courses}
    for key, name, slice_text in semester_slices:
        for c in courses:
            if c["code"] in slice_text and assigned[c["code"]] is None:
                assigned[c["code"]] = key
                c["sem"] = key

    pts = {"A": 4, "A-": 3.67, "B+": 3.33, "B": 3, "B-": 2.67,
           "C+": 2.33, "C": 2, "C-": 1.67, "D+": 1.33, "D": 1}
    sem_meta = {}
    for i, (key, name, _) in enumerate(semester_slices):
        sem_courses = [c for c in courses if c.get("sem") == key]
        graded = [c for c in sem_courses if c.get("score") and c.get("grade") not in ("P", "NP", "IP")]
        ip_count = sum(1 for c in sem_courses if c.get("grade") == "IP")
        total_credits = len(sem_courses) * 3
        avg_score = round(sum(c["score"] for c in graded) / len(graded), 2) if graded else None
        gpa = None
        if graded:
            weighted = sum(pts.get(c["grade"], 0) * 3 for c in graded)
            gpa = round(weighted / (len(graded) * 3), 2)
        sem_meta[key] = {
            "key": key, "name": name, "gpa": gpa, "avg": avg_score,
            "credits": total_credits, "courses": len(sem_courses),
            "color": SEM_COLOURS[i % len(SEM_COLOURS)],
            "current": ip_count > 0 and i == len(semester_slices) - 1,
        }

    return courses, list(sem_meta.values())


def _compute_stats(courses: list[dict]) -> dict:
    pts = {"A": 4, "A-": 3.67, "B+": 3.33, "B": 3, "B-": 2.67,
           "C+": 2.33, "C": 2, "C-": 1.67, "D+": 1.33, "D": 1}
    graded = [c for c in courses if c.get("score") and c.get("grade") not in ("P", "NP", "IP")]
    if not graded:
        return {"grand_gpa": None, "grand_average": None, "total_credits": 0, "in_progress_count": 0}
    weighted_pts   = sum(pts.get(c["grade"], 0) * 3 for c in graded)
    weighted_score = sum(c["score"] * 3 for c in graded)
    total_cred     = len(graded) * 3
    ip_count       = sum(1 for c in courses if c.get("grade") == "IP")
    return {
        "grand_gpa":       round(weighted_pts / total_cred, 2),
        "grand_average":   round(weighted_score / total_cred, 2),
        "total_credits":   total_cred,
        "in_progress_count": ip_count,
    }

@router.get("/dashboard")
def student_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_student(current_user)

    cv_records = (
        db.query(CVRecord)
        .filter(CVRecord.user_id == current_user.id)
        .order_by(CVRecord.created_at.desc())
        .all()
    )
    profile = db.query(StudentProfile).filter(StudentProfile.user_id == current_user.id).first()

    unique_skills = _get_all_skills(cv_records)
    career_goal   = profile.career_goal if profile else ""
    readiness     = _calculate_readiness(unique_skills, career_goal)
    missing       = _get_missing_skills(unique_skills, career_goal)
    courses = []
    if profile and profile.transcript_text:
        courses = _extract_courses_from_transcript(profile.transcript_text)
    roles = _recommend_roles_for_student(
        unique_skills,
        courses=courses,
        career_goal=career_goal,
        gpa=profile.gpa if profile else None,
    )

    return {
        "user": {
            "id":    current_user.id,
            "name":  current_user.name,
            "email": current_user.email,
            "role":  current_user.role,
        },
        "profile": {
            "university":    profile.university    if profile else None,
            "major":         profile.major         if profile else None,
            "year_of_study": profile.year_of_study if profile else None,
            "gpa":           profile.gpa           if profile else None,
            "career_goal":   career_goal,
        },
        "readiness_score":   readiness,
        "skills":            unique_skills,
        "skills_count":      len(unique_skills),
        "missing_skills":    missing,
        "recommended_roles": roles,
        "cv_uploaded":       len(cv_records),
        "last_cv": {
            "filename":    cv_records[0].filename,
            "skills":      json.loads(cv_records[0].extracted_skills) if cv_records[0].extracted_skills else [],
            "uploaded_at": cv_records[0].created_at.isoformat(),
        } if cv_records else None,
    }


@router.post("/upload-transcript")
async def upload_transcript(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_student(current_user)
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    content  = await file.read()
    raw_text = extract_text_from_pdf(content)
    if not raw_text or not raw_text.strip():
        raise HTTPException(status_code=422, detail="Could not extract text from PDF. Make sure it's not a scanned image.")
    is_transcript = _is_transcript(raw_text)
    courses: list[dict] = []
    semesters: list[dict] = []
    stats: dict = {}

    if is_transcript:
        courses = _extract_courses_from_transcript(raw_text)
        courses, semesters = _assign_semesters(raw_text, courses)
        stats = _compute_stats(courses)
    skills = extract_skills_from_text(raw_text)
    profile = db.query(StudentProfile).filter(StudentProfile.user_id == current_user.id).first()
    if profile:
        profile.transcript_text = raw_text[:3000]
        if stats.get("grand_gpa"):
            profile.gpa = stats["grand_gpa"]
    else:
        profile = StudentProfile(
            user_id=current_user.id,
            transcript_text=raw_text[:3000],
            gpa=stats.get("grand_gpa"),
        )
        db.add(profile)
    db.commit()

    cv_record = CVRecord(
        user_id=current_user.id,
        filename=file.filename,
        raw_text=raw_text[:5000],
        extracted_skills=json.dumps(skills),
    )
    db.add(cv_record)
    db.commit()
    db.refresh(cv_record)
    all_cv = (
        db.query(CVRecord)
        .filter(CVRecord.user_id == current_user.id)
        .all()
    )
    all_skills = _get_all_skills(all_cv)

    career_goal = profile.career_goal if profile else ""
    readiness   = _calculate_readiness(all_skills, career_goal)
    missing     = _get_missing_skills(all_skills, career_goal)
    roles = _recommend_roles_for_student(
        all_skills,
        courses=courses,
        career_goal=career_goal,
        gpa=profile.gpa if profile else None,
    )
    insight = await _groq_insight(current_user.name, courses, skills)

    return {
        "success":       True,
        "filename":      file.filename,
        "is_transcript": is_transcript,
        "cv_record_id":  cv_record.id,
        "uploaded_at":   cv_record.created_at.isoformat(),
        "skills_found":  skills,
        "skills_count":  len(skills),
        "all_skills":    all_skills,
        "grand_gpa":     stats.get("grand_gpa"),
        "grand_average": stats.get("grand_average"),
        "in_progress_count": stats.get("in_progress_count", 0),
        "semesters":     semesters,
        "courses":       courses,
        "readiness_score":   readiness,
        "missing_skills":    missing,
        "recommended_roles": roles,
        "insight": insight,
    }


@router.get("/skill-gap")
def skill_gap(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_student(current_user)

    cv_records = (
        db.query(CVRecord)
        .filter(CVRecord.user_id == current_user.id)
        .order_by(CVRecord.created_at.desc())
        .all()
    )
    profile     = db.query(StudentProfile).filter(StudentProfile.user_id == current_user.id).first()
    all_skills  = _get_all_skills(cv_records)
    career_goal = profile.career_goal if profile else ""

    if not career_goal:
        return {
            "has_goal":    False,
            "message":     "Set a career goal in your profile to see skill gap analysis.",
            "career_goal": "",
            "matched":     [], "missing": [], "extra": [],
            "match_pct":   0,
        }

    role_skills  = _get_role_skills(career_goal)
    skills_lower = [s.lower() for s in all_skills]

    matched = [rs for rs in role_skills if any(rs in sk or sk in rs for sk in skills_lower)]
    missing = [rs for rs in role_skills if rs not in matched]
    extra   = [sk for sk in all_skills if not any(rs in sk or sk in rs for rs in role_skills)]
    pct     = round(len(matched) / len(role_skills) * 100) if role_skills else 0

    return {
        "has_goal":    True,
        "career_goal": career_goal,
        "role_skills": role_skills,
        "matched":     matched,
        "missing":     missing,
        "extra":       extra,
        "match_pct":   pct,
        "skills_count": len(all_skills),
    }


@router.get("/roadmap")
async def get_roadmap(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_student(current_user)

    cv_records  = db.query(CVRecord).filter(CVRecord.user_id == current_user.id).all()
    profile     = db.query(StudentProfile).filter(StudentProfile.user_id == current_user.id).first()
    all_skills  = _get_all_skills(cv_records)
    career_goal = profile.career_goal if profile else ""
    missing     = _get_missing_skills(all_skills, career_goal)

    roadmap = []
    if career_goal and all_skills and missing:
        roadmap = await _groq_roadmap(all_skills, missing, career_goal)

    return {
        "target_role":    career_goal,
        "current_skills": all_skills,
        "missing_skills": missing,
        "roadmap":        roadmap,
    }


@router.post("/profile")
def update_profile(
    req: StudentProfileRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_student(current_user)
    profile = db.query(StudentProfile).filter(StudentProfile.user_id == current_user.id).first()

    data = req.dict(exclude_none=True)
    if profile:
        for field, val in data.items():
            setattr(profile, field, val)
    else:
        profile = StudentProfile(user_id=current_user.id, **data)
        db.add(profile)

    db.commit()
    db.refresh(profile)
    cv_records  = db.query(CVRecord).filter(CVRecord.user_id == current_user.id).all()
    all_skills  = _get_all_skills(cv_records)
    career_goal = profile.career_goal or ""
    missing     = _get_missing_skills(all_skills, career_goal)
    readiness   = _calculate_readiness(all_skills, career_goal)
    courses = []
    if profile.transcript_text:
        courses = _extract_courses_from_transcript(profile.transcript_text)
    roles = _recommend_roles_for_student(
        all_skills,
        courses=courses,
        career_goal=career_goal,
        gpa=profile.gpa,
    )

    return {
        "success":        True,
        "message":        "Profile updated",
        "missing_skills": missing,
        "readiness_score": readiness,
        "recommended_roles": roles,
    }


@router.get("/recommendations")
def get_recommendations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_student(current_user)
    cv_records = db.query(CVRecord).filter(CVRecord.user_id == current_user.id).all()
    profile = db.query(StudentProfile).filter(StudentProfile.user_id == current_user.id).first()
    all_skills = _get_all_skills(cv_records)
    courses = []
    if profile and profile.transcript_text:
        courses = _extract_courses_from_transcript(profile.transcript_text)
    roles = _recommend_roles_for_student(
        all_skills,
        courses=courses,
        career_goal=profile.career_goal if profile else "",
        gpa=profile.gpa if profile else None,
    )
    return {"skills": all_skills, "recommended_roles": roles}
