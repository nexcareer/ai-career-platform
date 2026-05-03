import re
from typing import List, Dict, Optional
from services.skill_extractor import ALL_SKILLS

SENIORITY_RANK = {"intern": 0, "junior": 1, "middle": 2, "senior": 3, "lead": 4}
RANK_SENIORITY = {v: k for k, v in SENIORITY_RANK.items()}


def normalize_seniority(value: Optional[str]) -> str:
    text = (value or "").lower()
    if not text:
        return "unknown"
    if re.search(r"\b(intern|internship|trainee|стаж[её]р|стажировка)\b", text):
        return "intern"
    if re.search(r"\b(junior|jr\.?|entry[ -]?level|beginner|джун|джуниор|младший)\b", text):
        return "junior"
    if re.search(r"\b(middle|mid\.?|mid[ -]?level|intermediate|мидл|средний)\b", text):
        return "middle"
    if re.search(r"\b(senior|sr\.?|сеньор|старший)\b", text):
        return "senior"
    if re.search(r"\b(lead|principal|architect|head|team lead|tech lead|лид|руководитель)\b", text):
        return "lead"
    return "unknown"


def extract_years_experience(text: Optional[str]) -> Optional[float]:
    text_lower = (text or "").lower()
    if not text_lower:
        return None

    range_patterns = [
        r"(?:experience|опыт|стаж)[^\d]{0,35}(\d+(?:[.,]\d+)?)\s*(?:[-–—]|to|до)\s*(\d+(?:[.,]\d+)?)",
        r"(\d+(?:[.,]\d+)?)\s*(?:[-–—]|to|до)\s*(\d+(?:[.,]\d+)?)\s*(?:years?|yrs?|лет|года|год)",
    ]
    for pattern in range_patterns:
        match = re.search(pattern, text_lower, flags=re.IGNORECASE)
        if match:
            try:
                return float(match.group(1).replace(",", "."))
            except ValueError:
                pass

    patterns = [
        r"(\d+(?:[.,]\d+)?)\s*\+?\s*(?:years?|yrs?|лет|года|год)\s+(?:of\s+)?(?:experience|опыта|коммерческого\s+опыта|работы)",
        r"(?:experience|опыт|стаж)[^\d]{0,25}(\d+(?:[.,]\d+)?)\s*\+?\s*(?:years?|yrs?|лет|года|год)",
        r"(?:experience|опыт|стаж)[^\d]{0,25}(\d+(?:[.,]\d+)?)",
        r"(\d+(?:[.,]\d+)?)\s*\+?\s*(?:y\.?o\.?e\.?|yoe)",
    ]
    values = []
    for pattern in patterns:
        for match in re.finditer(pattern, text_lower, flags=re.IGNORECASE):
            try:
                values.append(float(match.group(1).replace(",", ".")))
            except ValueError:
                continue
    return max(values) if values else None


def infer_seniority(text: Optional[str] = "", years: Optional[float] = None, fallback: Optional[str] = None) -> str:
    explicit = normalize_seniority(text)
    if explicit != "unknown":
        return explicit

    fallback_level = normalize_seniority(fallback)
    if fallback_level != "unknown":
        return fallback_level

    parsed_years = years if years is not None else extract_years_experience(text)
    if parsed_years is None:
        return "unknown"
    if parsed_years <= 1:
        return "junior"
    if parsed_years < 5:
        return "middle"
    return "senior"


def split_skills(value) -> List[str]:
    if isinstance(value, list):
        parts = value
    else:
        parts = re.split(r"[,;|]+", str(value or ""))

    result = []
    for skill in parts:
        normalized = re.sub(r"\s+", " ", str(skill or "").strip().lower())
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def seniority_match_score(candidate_level: str, job_level: str) -> tuple[float, str]:
    candidate = normalize_seniority(candidate_level)
    job = normalize_seniority(job_level)
    if candidate == "unknown" or job == "unknown":
        return 1.0, "unknown"

    candidate_rank = SENIORITY_RANK[candidate]
    job_rank = SENIORITY_RANK[job]
    diff = job_rank - candidate_rank
    if diff <= 0:
        return 1.0, "aligned"
    if diff == 1:
        if candidate == "junior" and job == "middle":
            return 0.65, "stretch"
        return 0.82, "stretch"
    return 0.45, "too_senior"


def calculate_match(
    cv_skills: List[str],
    job_description: str,
    required_skills: Optional[List[str] | str] = None,
    candidate_level: Optional[str] = None,
    job_level: Optional[str] = None,
) -> Dict:
    job_lower = job_description.lower()
    explicit_required_skills = split_skills(required_skills)
    required_skills = explicit_required_skills or [s for s in ALL_SKILLS if s in job_lower]
    normalized_cv_skills = split_skills(cv_skills)
    inferred_job_level = infer_seniority(job_description, fallback=job_level)
    seniority_factor, seniority_status = seniority_match_score(candidate_level or "unknown", inferred_job_level)

    if not required_skills:
        matched = normalized_cv_skills[:3] if normalized_cv_skills else []
        base_score = 50.0
        return {
            "score": round(base_score * seniority_factor, 1),
            "base_score": base_score,
            "matched": matched,
            "missing": [],
            "required_skills": [],
            "required_total": 0,
            "candidate_level": normalize_seniority(candidate_level),
            "job_level": inferred_job_level,
            "seniority_status": seniority_status,
        }

    matched = [s for s in required_skills if any(s in cv_skill or cv_skill in s for cv_skill in normalized_cv_skills)]
    missing = [s for s in required_skills if s not in matched]
    base_score = round(len(matched) / len(required_skills) * 100, 1)
    score = round(base_score * seniority_factor, 1)
    return {
        "score": score,
        "base_score": base_score,
        "matched": matched,
        "missing": missing[:8],
        "required_skills": required_skills,
        "required_total": len(required_skills),
        "candidate_level": normalize_seniority(candidate_level),
        "job_level": inferred_job_level,
        "seniority_status": seniority_status,
    }


def get_readiness_level(score: float) -> str:
    if score >= 80:
        return "high"
    elif score >= 60:
        return "medium"
    return "low"


def get_recommendation(score: float, missing: List[str]) -> str:
    if score >= 80:
        return f"Excellent match. You cover most requirements. Consider strengthening: {', '.join(missing[:3]) if missing else 'all key areas covered'}."
    elif score >= 60:
        gap = ", ".join(missing[:3]) if missing else "a few areas"
        return f"Good match with room to grow. Focus on: {gap}."
    else:
        gap = ", ".join(missing[:4]) if missing else "core technical skills"
        return f"Needs improvement. Prioritize learning: {gap}."
