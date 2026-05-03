import csv
import json
import os
import re
from collections import Counter
from functools import lru_cache

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from models import CVRecord, MatchResult, User
from services.hh_api import DEMO_JOBS, fetch_hh_jobs, search_local_dataset
from services.matching import calculate_match, get_readiness_level, split_skills
from services.skill_extractor import extract_skills_from_text, extract_text_from_pdf

router = APIRouter(prefix="/jobs", tags=["Jobs"])

CSV_FALLBACK = os.path.join(os.path.dirname(os.path.dirname(__file__)), "telegram_all_posts.csv")
CITY_ALIASES = {
    "Almaty": ["алматы", "almaty"],
    "Astana": ["астана", "astana", "нур-султан", "nur-sultan"],
    "Shymkent": ["шымкент", "shymkent"],
    "Tashkent": ["ташкент", "tashkent"],
    "Aktau": ["актау", "aktau"],
    "Aktobe": ["актобе", "aktobe"],
    "Karaganda": ["караганда", "karaganda"],
    "Remote": ["удаленно", "удалённо", "remote", "онлайн"],
}


def _as_text(value):
    return "" if value is None else str(value).strip()


def _format_salary(row):
    salary_min = _as_text(row.get("salary_min"))
    salary_max = _as_text(row.get("salary_max"))
    currency = _as_text(row.get("currency"))
    parts = []
    if salary_min:
        parts.append(_format_number(salary_min))
    if salary_max:
        parts.append(_format_number(salary_max))
    if not parts:
        return _extract_salary(_as_text(row.get("description")))
    salary = " - ".join(parts)
    return f"{salary} {currency}".strip()


def _format_number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number.is_integer():
        return f"{int(number):,}".replace(",", " ")
    return str(number)


def _combined_text(row):
    return " ".join(
        _as_text(row.get(field))
        for field in [
            "title",
            "company",
            "city",
            "country",
            "format",
            "employment",
            "seniority",
            "required_skills",
            "nice_to_have_skills",
            "responsibilities",
            "requirements",
            "description",
        ]
    )


def _safe_json_list(value):
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value or "[]")
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


def _extract_city(text):
    text_lower = (text or "").lower()
    for city, needles in CITY_ALIASES.items():
        if any(needle in text_lower for needle in needles):
            return city
    return ""


def _city_matches(job, city):
    haystack = " ".join([str(job.get("city", "")), str(job.get("country", "")), str(job.get("text", ""))]).lower()
    variants = [city]
    for canonical, aliases in CITY_ALIASES.items():
        if city == canonical.lower() or city in aliases:
            variants.extend(aliases)
            variants.append(canonical.lower())
    return any(variant and variant in haystack for variant in variants)


def _extract_salary(text):
    patterns = [
        r"(?:до|от|from|salary|зп|зарплата)[:\s-]*([^\n]{1,80}(?:₸|тенге|kzt|\$|usd|eur|€)[^\n]{0,40})",
        r"(\d[\d\s.,]{2,}\s*(?:-|–|—)\s*\d[\d\s.,]{2,}\s*(?:₸|тенге|kzt|\$|usd|eur|€)?)",
        r"(\d[\d\s.,]{2,}\s*(?:₸|тенге|kzt|\$|usd|eur|€))",
    ]
    for pattern in patterns:
        match = re.search(pattern, text or "", re.IGNORECASE)
        if match:
            return match.group(1).strip()[:255]
    return ""


def _extract_work_format(text):
    text_lower = (text or "").lower()
    if any(word in text_lower for word in ["remote", "удаленно", "удалённо", "онлайн"]):
        return "Remote"
    if any(word in text_lower for word in ["hybrid", "гибрид"]):
        return "Hybrid"
    if any(word in text_lower for word in ["office", "офис", "офлайн"]):
        return "Office"
    return ""


def _extract_position(text):
    lines = [line.strip(" *#-•") for line in (text or "").splitlines() if line.strip()]
    if not lines:
        return ""
    return re.sub(r"\s+", " ", lines[0])[:255]


def _csv_job_from_row(index, row):
    text = _combined_text(row)
    required = split_skills(row.get("required_skills"))
    nice = split_skills(row.get("nice_to_have_skills"))
    extracted = split_skills(required + nice)
    if not extracted:
        extracted = split_skills(extract_skills_from_text(text))
    title = _as_text(row.get("title")) or _extract_position(_as_text(row.get("description")))
    return {
        "id": _as_text(row.get("id")) or f"csv-{index}",
        "channel": "telegram",
        "position": title,
        "company": _as_text(row.get("company")),
        "city": _as_text(row.get("city")) or _extract_city(text),
        "country": _as_text(row.get("country")),
        "salary": _format_salary(row),
        "salary_min": _as_text(row.get("salary_min")),
        "salary_max": _as_text(row.get("salary_max")),
        "currency": _as_text(row.get("currency")),
        "work_format": _as_text(row.get("format")) or _extract_work_format(text),
        "employment": _as_text(row.get("employment")),
        "experience": _as_text(row.get("seniority")),
        "seniority": _as_text(row.get("seniority")),
        "views": int(float(row.get("views") or 0)),
        "date": row.get("date", ""),
        "telegram_url": _as_text(row.get("source_url")),
        "url": _as_text(row.get("source_url")),
        "text": text,
        "required_skills": required,
        "nice_to_have_skills": nice,
        "responsibilities": _as_text(row.get("responsibilities")),
        "requirements": _as_text(row.get("requirements")),
        "description": _as_text(row.get("description")),
        "extracted_skills": extracted,
    }


@lru_cache(maxsize=1)
def _load_csv_telegram_jobs():
    if not os.path.exists(CSV_FALLBACK):
        return []
    with open(CSV_FALLBACK, "r", encoding="utf-8", newline="") as file:
        return [_csv_job_from_row(i, row) for i, row in enumerate(csv.DictReader(file), start=1)]


def _filter_telegram_jobs(jobs, q="", city="", skill="", work_format="", seniority=""):
    q = q.lower().strip()
    city = city.lower().strip()
    skill = skill.lower().strip()
    work_format = work_format.lower().strip()
    seniority = seniority.lower().strip()
    filtered = jobs
    if q:
        filtered = [
            job for job in filtered
            if q in " ".join([
                str(job.get("position", "")),
                str(job.get("company", "")),
                str(job.get("city", "")),
                str(job.get("country", "")),
                str(job.get("seniority", "")),
                " ".join(job.get("required_skills", [])),
                str(job.get("text", "")),
            ]).lower()
        ]
    if city:
        filtered = [job for job in filtered if _city_matches(job, city)]
    if skill:
        filtered = [
            job for job in filtered
            if any(skill in str(item).lower() for item in job.get("extracted_skills", []) + job.get("required_skills", []))
        ]
    if work_format:
        filtered = [job for job in filtered if work_format in str(job.get("work_format", "")).lower()]
    if seniority:
        filtered = [job for job in filtered if seniority in str(job.get("seniority", "")).lower()]
    return filtered


@router.get("/search")
def search_jobs(
    query: str = "python developer",
    area: int = 160,
    per_page: int = 10,
    current_user: User = Depends(get_current_user),
):
    jobs = fetch_hh_jobs(query, area, per_page) or DEMO_JOBS
    source = jobs[0].get("source", "unknown") if jobs else "unknown"
    return {"query": query, "total": len(jobs), "source": source, "jobs": jobs}


@router.get("/dataset")
def dataset_jobs(
    query: str = "python",
    limit: int = 20,
    current_user: User = Depends(get_current_user),
):
    jobs = search_local_dataset(query, per_page=limit)
    return {"query": query, "source": "local_dataset", "total": len(jobs), "jobs": jobs}


@router.post("/match")
async def match_cv_to_jobs(
    file: UploadFile = File(...),
    job_query: str = Form(default="python developer"),
    area: int = Form(default=160),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    content = await file.read()
    text = extract_text_from_pdf(content)
    cv_skills = extract_skills_from_text(text) or ["general skills"]
    jobs = fetch_hh_jobs(job_query, area, per_page=15) or DEMO_JOBS

    scored_jobs = []
    for job in jobs:
        job_text = (
            f"{job['title']} {job.get('requirement', '')} "
            f"{job.get('responsibility', '')} {job.get('key_skills', '')}"
        )
        match = calculate_match(cv_skills, job_text)
        scored_jobs.append({
            **job,
            "match_score": match["score"],
            "matched_skills": match["matched"],
            "missing_skills": match["missing"],
        })

    scored_jobs.sort(key=lambda x: x["match_score"], reverse=True)

    record = CVRecord(
        user_id=current_user.id,
        filename=file.filename,
        raw_text=text[:5000],
        extracted_skills=json.dumps(cv_skills),
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    match_log = MatchResult(
        user_id=current_user.id,
        cv_record_id=record.id,
        job_query=job_query,
        match_score=scored_jobs[0]["match_score"] if scored_jobs else 0,
        matched_skills=json.dumps(scored_jobs[0]["matched_skills"] if scored_jobs else []),
        missing_skills=json.dumps(scored_jobs[0]["missing_skills"] if scored_jobs else []),
        results_json=json.dumps({"cv_skills": cv_skills, "jobs_count": len(scored_jobs)}),
    )
    db.add(match_log)
    db.commit()

    avg_score = round(sum(j["match_score"] for j in scored_jobs) / len(scored_jobs), 1) if scored_jobs else 0
    return {
        "cv_skills": cv_skills,
        "cv_skills_count": len(cv_skills),
        "jobs": scored_jobs,
        "total_jobs": len(scored_jobs),
        "top_match": scored_jobs[0] if scored_jobs else None,
        "average_score": avg_score,
        "query": job_query,
    }


@router.get("/telegram")
def get_telegram_jobs(
    q: str = "",
    city: str = "",
    skill: str = "",
    format: str = "",
    seniority: str = "",
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        from models import TelegramJob
    except ImportError:
        raise HTTPException(status_code=503, detail="TelegramJob model not available")

    query = db.query(TelegramJob)
    if query.count() == 0:
        jobs = _filter_telegram_jobs(_load_csv_telegram_jobs(), q=q, city=city, skill=skill, work_format=format, seniority=seniority)
        jobs.sort(key=lambda job: job.get("views", 0), reverse=True)
        return {"total": len(jobs), "returned": len(jobs[:limit]), "jobs": jobs[:limit], "source": "csv"}

    if q:
        q_lower = f"%{q.lower()}%"
        query = query.filter(
            (TelegramJob.position.ilike(q_lower)) |
            (TelegramJob.text.ilike(q_lower)) |
            (TelegramJob.company.ilike(q_lower))
        )
    if city:
        query = query.filter(TelegramJob.city.ilike(f"%{city}%"))
    if skill:
        query = query.filter(TelegramJob.extracted_skills.ilike(f"%{skill.lower()}%"))
    if format:
        query = query.filter(TelegramJob.work_format.ilike(f"%{format}%"))
    if seniority:
        query = query.filter(TelegramJob.experience.ilike(f"%{seniority}%"))

    total = query.count()
    jobs = query.order_by(TelegramJob.views.desc()).limit(limit).all()
    return {
        "total": total,
        "returned": len(jobs),
        "source": "database",
        "jobs": [
            {
                "id": j.id,
                "channel": j.channel,
                "position": j.position,
                "company": j.company,
                "city": j.city,
                "salary": j.salary,
                "work_format": j.work_format,
                "experience": j.experience,
                "seniority": j.experience,
                "views": j.views,
                "date": j.date,
                "telegram_url": j.telegram_url,
                "url": j.url,
                "extracted_skills": _safe_json_list(j.extracted_skills),
                "required_skills": _safe_json_list(j.extracted_skills),
            }
            for j in jobs
        ],
    }


@router.get("/telegram/stats")
def telegram_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        from models import TelegramJob
    except ImportError:
        raise HTTPException(status_code=503, detail="TelegramJob model not available")

    total = db.query(TelegramJob).count()
    if total == 0:
        jobs = _load_csv_telegram_jobs()
        channels = Counter(job.get("channel") for job in jobs if job.get("channel"))
        cities = Counter(job.get("city") for job in jobs if job.get("city"))
        skills = Counter(skill for job in jobs for skill in job.get("extracted_skills", []))
        avg_views = round(sum(job.get("views", 0) for job in jobs) / len(jobs), 1) if jobs else 0
        return {
            "total": len(jobs),
            "by_channel": dict(channels),
            "top_cities": [{"city": city, "count": count} for city, count in cities.most_common(10)],
            "top_skills": [{"skill": skill, "count": count} for skill, count in skills.most_common(15)],
            "avg_views": avg_views,
            "source": "csv",
        }

    from sqlalchemy import func
    channel_rows = db.query(TelegramJob.channel, func.count(TelegramJob.id)).group_by(TelegramJob.channel).all()
    city_rows = (
        db.query(TelegramJob.city, func.count(TelegramJob.id))
        .filter(TelegramJob.city != None, TelegramJob.city != "")
        .group_by(TelegramJob.city)
        .order_by(func.count(TelegramJob.id).desc())
        .limit(10)
        .all()
    )
    skills = Counter()
    for (skills_json,) in db.query(TelegramJob.extracted_skills).all():
        skills.update(_safe_json_list(skills_json))

    avg_views_row = db.query(func.avg(TelegramJob.views)).scalar()
    avg_views = round(float(avg_views_row), 1) if avg_views_row else 0
    return {
        "total": total,
        "by_channel": {row[0]: row[1] for row in channel_rows},
        "top_cities": [{"city": row[0], "count": row[1]} for row in city_rows],
        "top_skills": [{"skill": skill, "count": count} for skill, count in skills.most_common(15)],
        "avg_views": avg_views,
        "source": "database",
    }


@router.post("/telegram/import-csv")
def import_telegram_csv(
    path: str = "telegram_all_posts.csv",
    current_user: User = Depends(get_current_user),
):
    _require_employer_or_admin(current_user)
    if not os.path.exists(path):
        backend_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), path)
        if os.path.exists(backend_path):
            path = backend_path
        else:
            raise HTTPException(status_code=404, detail=f"CSV file not found: {path}")
    try:
        from services.telegram_jobs import import_csv_to_db
        result = import_csv_to_db(path)
        return {"success": True, **result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


def _require_employer_or_admin(user: User):
    if user.role not in ("employer", "admin"):
        raise HTTPException(status_code=403, detail="Employer access required")


def _get_market_job(job_id: str, db: Session):
    try:
        from models import TelegramJob
        db_job = db.query(TelegramJob).filter(TelegramJob.id == int(job_id)).first()
    except Exception:
        db_job = None

    if db_job:
        skills = _safe_json_list(db_job.extracted_skills)
        return {
            "id": str(db_job.id),
            "position": db_job.position or "",
            "company": db_job.company or "",
            "description": db_job.text or "",
            "required_skills": skills,
            "text": " ".join([db_job.position or "", db_job.text or "", " ".join(skills)]),
        }

    normalized_id = job_id.replace("csv-", "")
    for job in _load_csv_telegram_jobs():
        if str(job.get("id")) == normalized_id or str(job.get("id")) == job_id:
            return job
    return None


@router.post("/telegram/{job_id}/match-candidates")
def match_market_job_to_candidates(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_employer_or_admin(current_user)
    job = _get_market_job(job_id, db)
    if not job:
        raise HTTPException(status_code=404, detail="Market vacancy not found")

    candidates = db.query(User).filter(User.role.in_(["student", "professional"])).all()
    results = []
    for candidate in candidates:
        records = db.query(CVRecord).filter(CVRecord.user_id == candidate.id).order_by(CVRecord.created_at.desc()).all()
        if not records:
            continue
        candidate_skills = []
        for record in records:
            if record.extracted_skills:
                candidate_skills.extend(_safe_json_list(record.extracted_skills))
        match = calculate_match(candidate_skills, job.get("text", ""), job.get("required_skills"))
        results.append({
            "candidate_id": candidate.id,
            "name": candidate.name,
            "role": candidate.role,
            "skills": sorted(set(candidate_skills)),
            "match_score": match["score"],
            "matched_skills": match["matched"],
            "missing_skills": match["missing"],
            "required_skills": match["required_skills"],
            "readiness_level": get_readiness_level(match["score"]),
        })

    results.sort(key=lambda item: item["match_score"], reverse=True)
    return {
        "job_title": job.get("position") or "Market vacancy",
        "total_candidates": len(results),
        "required_skills": job.get("required_skills", []),
        "candidates": results,
    }
