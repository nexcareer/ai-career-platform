import json
import os
import hashlib
from pathlib import Path
from typing import Dict, List, Optional

import requests

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:
    pass


GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "llama-3.3-70b-versatile"
_MATCH_CACHE: dict[str, Dict] = {}
_LAST_ERROR = ""


def groq_enabled() -> bool:
    return bool(os.getenv("GROQ_API_KEY"))


def groq_status() -> Dict:
    return {"enabled": groq_enabled(), "last_error": _LAST_ERROR}


def _clip(text: str, limit: int) -> str:
    text = (text or "").strip()
    return text[:limit]


def analyze_cv_job_match(
    cv_text: str,
    job_text: str,
    cv_skills: List[str],
    heuristic: Dict,
) -> Optional[Dict]:
    global _LAST_ERROR
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        _LAST_ERROR = "GROQ_API_KEY is missing"
        return None

    model = os.getenv("GROQ_MODEL", DEFAULT_MODEL)
    cache_key = hashlib.sha256(
        json.dumps(
            {
                "cv": _clip(cv_text, 4500),
                "job": _clip(job_text, 3500),
                "skills": cv_skills[:30],
                "model": model,
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    if cache_key in _MATCH_CACHE:
        return dict(_MATCH_CACHE[cache_key])

    prompt = {
        "cv_text": _clip(cv_text, 4500),
        "job_description": _clip(job_text, 3500),
        "extracted_cv_skills": cv_skills[:30],
        "heuristic_match": heuristic,
    }
    messages = [
        {
            "role": "system",
            "content": (
                "You are a strict HR matching engine. Compare CV to job using experience level, "
                "years of experience, skills, and projects. Return only valid JSON with keys: "
                "match_score number 0-100, candidate_level, job_level, seniority_status "
                "one of aligned/stretch/too_senior/too_junior/unknown, matched_skills array, "
                "missing_skills array, project_fit one of strong/partial/weak/unknown, reason string. "
                "If candidate has 0 years but no explicit internship text, treat candidate as junior. "
                "If job asks 3+ years or 3-6 years, it is at least middle. Lead/principal/head roles are lead."
            ),
        },
        {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
    ]

    try:
        response = requests.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": messages,
                "temperature": 0,
                "response_format": {"type": "json_object"},
            },
            timeout=12,
        )
        if response.status_code >= 400:
            try:
                detail = response.json().get("error", {}).get("message", response.text)
            except Exception:
                detail = response.text
            _LAST_ERROR = f"Groq API error {response.status_code}: {detail[:180]}"
            return None
        content = response.json()["choices"][0]["message"]["content"]
        data = json.loads(content)
        _LAST_ERROR = ""
    except Exception as exc:
        _LAST_ERROR = f"Groq request failed: {exc}"
        return None

    try:
        score = float(data.get("match_score", heuristic.get("score", 0)))
    except (TypeError, ValueError):
        score = heuristic.get("score", 0)

    data["match_score"] = max(0, min(100, round(score, 1)))
    data["matched_skills"] = data.get("matched_skills") or heuristic.get("matched", [])
    data["missing_skills"] = data.get("missing_skills") or heuristic.get("missing", [])
    data["candidate_level"] = data.get("candidate_level") or heuristic.get("candidate_level", "unknown")
    data["job_level"] = data.get("job_level") or heuristic.get("job_level", "unknown")
    data["seniority_status"] = data.get("seniority_status") or heuristic.get("seniority_status", "unknown")
    data["source"] = "groq"
    _MATCH_CACHE[cache_key] = dict(data)
    return data
