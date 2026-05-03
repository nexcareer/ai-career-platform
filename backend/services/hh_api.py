import csv
import json
import glob
import re
import requests
from pathlib import Path
from typing import List, Dict

HH_API_BASE = "https://api.hh.ru"
_LOCAL_DATASET: List[Dict] = []
_TELEGRAM_DATASET: List[Dict] = []
TELEGRAM_CSV_PATH = Path(__file__).resolve().parents[1] / "telegram_all_jobs.csv"


def _load_local_dataset() -> List[Dict]:
    all_jobs = []
    for path in glob.glob("hh_kz_vacancies_*.json"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                items = json.load(f)
                if isinstance(items, list):
                    all_jobs.extend(items)
        except Exception:
            pass
    return all_jobs


def _get_local_dataset() -> List[Dict]:
    global _LOCAL_DATASET
    if not _LOCAL_DATASET:
        _LOCAL_DATASET = _load_local_dataset()
    return _LOCAL_DATASET


def _clean_telegram_text(text: str) -> str:
    text = re.sub(r"\*\*|__|`", "", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_telegram_title(text: str) -> str:
    clean = _clean_telegram_text(text)
    patterns = [
        r"(?:должность|позиция|position|role)\s*[:\-]\s*([^.;\n\r|•]{3,90})",
        r"#вакансия[^\wа-яА-Я]+([^|•\n\r]{3,90})",
    ]
    for pattern in patterns:
        match = re.search(pattern, clean, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip(" -:|•")
    first = re.sub(r"#[\wа-яА-ЯёЁ_]+", "", clean).strip()
    return (first[:90].rsplit(" ", 1)[0] or first[:90] or "Telegram vacancy").strip()


def _extract_telegram_company(text: str, channel: str) -> str:
    clean = _clean_telegram_text(text)
    match = re.search(r"(?:компания|company)\s*[:\-]\s*([^.;\n\r|•]{2,80})", clean, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip(" -:|•")
    return f"@{channel}" if channel else "Telegram"


def _extract_telegram_area(text: str) -> str:
    clean = _clean_telegram_text(text).lower()
    for city in ["алматы", "астана", "астана", "remote", "удален", "удалён", "онлайн", "hybrid", "гибрид"]:
        if city in clean:
            if city in {"удален", "удалён", "remote", "онлайн"}:
                return "Remote"
            if city == "гибрид":
                return "Hybrid"
            return "Astana" if city in {"астана", "астана"} else "Almaty"
    return "Kazakhstan"


def _extract_telegram_salary(text: str) -> str:
    clean = _clean_telegram_text(text)
    match = re.search(
        r"((?:от\s*)?\d[\d\s.,]*(?:\s*[-–]\s*\d[\d\s.,]*)?\s*(?:₸|тг|тенге|kzt|usd|\$))",
        clean,
        flags=re.IGNORECASE,
    )
    return match.group(1).strip() if match else "Not specified"


def _load_telegram_dataset() -> List[Dict]:
    print(f"Telegram CSV path: {TELEGRAM_CSV_PATH}", flush=True)
    print(f"Telegram CSV exists: {TELEGRAM_CSV_PATH.exists()}", flush=True)
    if not TELEGRAM_CSV_PATH.exists():
        return []

    jobs = []
    with open(TELEGRAM_CSV_PATH, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            text = _clean_telegram_text(row.get("text", ""))
            if not text:
                continue
            jobs.append({
                "id": f"tg-{row.get('channel', '')}-{row.get('message_id', '')}",
                "title": _extract_telegram_title(text),
                "company": _extract_telegram_company(text, row.get("channel", "")),
                "area": _extract_telegram_area(text),
                "salary": _extract_telegram_salary(text),
                "url": row.get("telegram_url", "#"),
                "requirement": text[:700],
                "responsibility": "",
                "experience": "",
                "schedule": "",
                "published": (row.get("date", "") or "")[:10],
                "source": "telegram_csv",
                "key_skills": text,
                "views": row.get("views"),
                "_search_text": text.lower(),
            })
    print(f"Loaded Telegram jobs: {len(jobs)}", flush=True)
    return jobs


def _get_telegram_dataset() -> List[Dict]:
    global _TELEGRAM_DATASET
    if not _TELEGRAM_DATASET:
        _TELEGRAM_DATASET = _load_telegram_dataset()
    return _TELEGRAM_DATASET


def search_telegram_dataset(query: str, per_page: int = 15) -> List[Dict]:
    dataset = _get_telegram_dataset()
    query_lower = query.lower()
    query_words = [w for w in re.split(r"\s+", query_lower) if len(w) > 2]
    scored = []

    for item in dataset:
        text = " ".join([
            item.get("title", ""),
            item.get("company", ""),
            item.get("area", ""),
            item.get("_search_text", ""),
        ]).lower()
        score = sum(3 for w in query_words if w in item.get("title", "").lower())
        score += sum(1 for w in query_words if w in text)
        if query_lower and query_lower in text:
            score += 5
        if score > 0:
            scored.append((score, item))

    scored.sort(key=lambda x: (x[0], x[1].get("published", "")), reverse=True)
    results = []
    for _, item in scored[:per_page]:
        clean = {k: v for k, v in item.items() if not k.startswith("_")}
        results.append(clean)
    return results


def get_telegram_dataset(limit: int | None = None) -> List[Dict]:
    dataset = _get_telegram_dataset()
    items = dataset if limit is None else dataset[:limit]
    return [{k: v for k, v in item.items() if not k.startswith("_")} for item in items]


def _format_local_job(item: Dict) -> Dict:
    sf = item.get("salary_from")
    st = item.get("salary_to")
    cur = item.get("currency") or "KZT"
    if sf and st:
        salary_str = f"{int(sf):,}–{int(st):,} {cur}"
    elif sf:
        salary_str = f"from {int(sf):,} {cur}"
    elif st:
        salary_str = f"up to {int(st):,} {cur}"
    else:
        salary_str = "Not specified"

    return {
        "id": item.get("id", ""),
        "title": item.get("title", ""),
        "company": item.get("company", "Company"),
        "area": item.get("city", "Kazakhstan"),
        "salary": salary_str,
        "url": item.get("url", "#"),
        "requirement": item.get("requirement", "") or "",
        "responsibility": item.get("responsibility", "") or "",
        "experience": item.get("experience", ""),
        "schedule": item.get("schedule", ""),
        "published": (item.get("published_at", "") or "")[:10],
        "source": "local_dataset",
        "key_skills": item.get("key_skills_text", "") or "",
    }


def search_local_dataset(query: str, per_page: int = 15) -> List[Dict]:
    dataset = _get_local_dataset()
    query_lower = query.lower()
    query_words = [w for w in query_lower.split() if len(w) > 2]
    scored = []
    for item in dataset:
        text = " ".join([
            item.get("title", ""),
            item.get("requirement", "") or "",
            item.get("responsibility", "") or "",
            item.get("key_skills_text", "") or "",
            item.get("source_query", ""),
        ]).lower()
        score = sum(1 for w in query_words if w in text)
        if score > 0:
            scored.append((score, item))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [_format_local_job(item) for _, item in scored[:per_page]]


def fetch_hh_jobs(query: str, area: int = 160, per_page: int = 15) -> List[Dict]:
    try:
        response = requests.get(
            f"{HH_API_BASE}/vacancies",
            params={"text": query, "area": area, "per_page": per_page, "order_by": "relevance"},
            headers={"User-Agent": "NexCareer/2.0 (capstone@sdu.edu.kz)"},
            timeout=10,
        )
        if response.status_code != 200:
            return search_local_dataset(query, per_page)

        jobs = []
        for item in response.json().get("items", []):
            salary = item.get("salary")
            salary_str = "Not specified"
            if salary:
                sf = salary.get("from")
                st = salary.get("to")
                cur = salary.get("currency", "KZT")
                if sf and st:
                    salary_str = f"{sf:,}–{st:,} {cur}"
                elif sf:
                    salary_str = f"from {sf:,} {cur}"
                elif st:
                    salary_str = f"up to {st:,} {cur}"

            snippet = item.get("snippet", {})
            req = (snippet.get("requirement", "") or "").replace("<highlighttext>", "").replace("</highlighttext>", "")
            resp = (snippet.get("responsibility", "") or "").replace("<highlighttext>", "").replace("</highlighttext>", "")

            jobs.append({
                "id": item["id"],
                "title": item["name"],
                "company": item.get("employer", {}).get("name", "Company"),
                "area": item.get("area", {}).get("name", ""),
                "salary": salary_str,
                "url": item.get("alternate_url", "#"),
                "requirement": req,
                "responsibility": resp,
                "experience": item.get("experience", {}).get("name", ""),
                "schedule": item.get("schedule", {}).get("name", ""),
                "published": (item.get("published_at", "") or "")[:10],
                "source": "hh_api",
                "key_skills": "",
            })
        return jobs
    except Exception:
        return search_local_dataset(query, per_page)


DEMO_JOBS = [
    {
        "id": "demo1", "title": "Python Backend Developer", "company": "Kaspi.kz",
        "area": "Almaty", "salary": "600,000–1,000,000 KZT", "url": "https://hh.kz",
        "requirement": "Python, FastAPI, PostgreSQL, Docker, Redis",
        "responsibility": "Backend services development",
        "experience": "1–3 years", "schedule": "Full day", "published": "2026-01-01",
        "source": "demo", "key_skills": "python fastapi postgresql docker redis",
    },
    {
        "id": "demo2", "title": "Data Analyst", "company": "Halyk Bank",
        "area": "Almaty", "salary": "400,000–700,000 KZT", "url": "https://hh.kz",
        "requirement": "SQL, Python, Pandas, Excel, Power BI, Tableau",
        "responsibility": "Data analysis and dashboard creation",
        "experience": "1–3 years", "schedule": "Remote", "published": "2026-01-01",
        "source": "demo", "key_skills": "sql python pandas excel power bi tableau",
    },
    {
        "id": "demo3", "title": "Frontend Developer", "company": "Jusan Bank",
        "area": "Astana", "salary": "500,000–800,000 KZT", "url": "https://hh.kz",
        "requirement": "JavaScript, React, TypeScript, HTML, CSS, Git",
        "responsibility": "UI development",
        "experience": "1–3 years", "schedule": "Full day", "published": "2026-01-01",
        "source": "demo", "key_skills": "javascript react typescript html css git",
    },
    {
        "id": "demo4", "title": "ML Engineer", "company": "Kcell",
        "area": "Almaty", "salary": "700,000–1,200,000 KZT", "url": "https://hh.kz",
        "requirement": "Python, TensorFlow, PyTorch, Scikit-learn, SQL, Docker",
        "responsibility": "Model development and deployment",
        "experience": "2–5 years", "schedule": "Full day", "published": "2026-01-01",
        "source": "demo", "key_skills": "python tensorflow pytorch scikit-learn sql docker",
    },
]
