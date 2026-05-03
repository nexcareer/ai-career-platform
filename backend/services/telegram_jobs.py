import os
import re
import json
import argparse
import csv
from datetime import datetime
from typing import List, Dict, Optional
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

TG_API_ID: Optional[int] = int(os.getenv("TG_API_ID", "0")) or None
TG_API_HASH: Optional[str] = os.getenv("TG_API_HASH") or None
TG_PHONE: Optional[str] = os.getenv("TG_PHONE") or None

SESSION_FILE = "tg_jobs_session"
CSV_PATH = "telegram_jobs_all_channels.csv"
CHANNELS = [
    "https://t.me/it_jobs_kz",
    "https://t.me/hh_kz_jobs",
    "https://t.me/devjobs_kz",
]

CSV_FIELDS = [
    "channel", "message_id", "date", "views", "telegram_url",
    "position", "company", "city", "salary", "work_format",
    "experience", "url", "text", "extracted_skills",
]
try:
    from services.skill_extractor import ALL_SKILLS
except ImportError:
    ALL_SKILLS = [
        "python", "javascript", "typescript", "java", "sql", "react", "docker",
        "kubernetes", "aws", "postgresql", "mongodb", "django", "fastapi", "git",
        "machine learning", "pandas", "tensorflow", "pytorch",
    ]

def clean_text(text: str) -> str:
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[*_`#~|>]", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def is_job_post(text: str) -> bool:
    keywords = [
        r"\bвакансия\b", r"\bjob\b", r"\bпозиция\b", r"\bнабираем\b",
        r"\bищем\b", r"\bопыт\s+работы\b", r"\bзарплата\b",
        r"\bсалари\b", r"\bsalary\b", r"\bremote\b", r"\bудалённо\b",
        r"\bфронтенд\b", r"\bбэкенд\b", r"\bdeveloper\b", r"\bengineer\b",
        r"\bразработчик\b", r"\baналитик\b", r"\banalyst\b",
    ]
    text_lower = text.lower()
    return sum(1 for kw in keywords if re.search(kw, text_lower)) >= 2

def extract_position(text: str) -> str:
    patterns = [
        r"(?:вакансия|позиция|ищем)[:\s]+([^\n]{3,60})",
        r"(?:vacancy|position|role)[:\s]+([^\n]{3,60})",
        r"^([^\n]{5,60}(?:developer|engineer|analyst|manager|designer|devops|scientist))",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE | re.MULTILINE)
        if m:
            return m.group(1).strip()[:255]
    for line in text.splitlines():
        line = line.strip()
        if 5 < len(line) < 80:
            return line[:255]
    return ""


def extract_company(text: str) -> str:
    patterns = [
        r"(?:компания|company|работодатель)[:\s]+([^\n]{2,100})",
        r"(?:в компанию|at|@)\s+([A-Z][A-Za-z0-9 &.,-]{1,60})",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(1).strip()[:255]
    return ""


def extract_city(text: str) -> str:
    cities = [
        "Almaty", "Алматы", "Astana", "Астана", "Shymkent", "Шымкент",
        "Aktau", "Актау", "Aktobe", "Актобе", "Karaganda", "Караганда",
        "Remote", "Удалённо", "Удаленно", "Онлайн",
    ]
    for city in cities:
        if re.search(r"\b" + re.escape(city) + r"\b", text, re.IGNORECASE):
            return city
    return ""


def extract_salary(text: str) -> str:
    patterns = [
        r"(\d[\d\s,]*(?:000)?)\s*[-–]\s*(\d[\d\s,]*(?:000)?)\s*(KZT|USD|EUR|₸|\$|€)",
        r"(?:от|from)\s*(\d[\d\s,]*)\s*(KZT|USD|EUR|₸|\$|€)",
        r"(?:зарплата|salary)[:\s]+([^\n]{3,60})",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(0).strip()[:255]
    return ""


def extract_work_format(text: str) -> str:
    formats = {
        "Remote": [r"\bremote\b", r"\bудалённо\b", r"\bудаленно\b", r"\bонлайн\b"],
        "Office": [r"\boffice\b", r"\bофис\b", r"\bв офисе\b"],
        "Hybrid": [r"\bhybrid\b", r"\bгибрид\b", r"\bгибридный\b"],
    }
    text_lower = text.lower()
    for fmt, patterns in formats.items():
        if any(re.search(p, text_lower) for p in patterns):
            return fmt
    return ""


def extract_experience(text: str) -> str:
    patterns = [
        r"(\d+\+?\s*(?:year|год|лет)[a-z]*\s*(?:of\s+)?(?:experience|опыта)?)",
        r"(?:опыт|experience)[:\s]+([^\n]{3,50})",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(1).strip()[:100]
    return ""


def extract_url(text: str) -> str:
    m = re.search(r"https?://\S+", text)
    return m.group(0)[:500] if m else ""


def extract_skills(text: str) -> List[str]:
    text_lower = text.lower()
    return [s for s in ALL_SKILLS if s in text_lower]


def parse_message(msg_text: str, channel: str, message_id: int,
                  date: str, views: int, msg_url: str) -> Dict:
    cleaned = clean_text(msg_text)
    return {
        "channel": channel,
        "message_id": message_id,
        "date": date,
        "views": views,
        "telegram_url": msg_url,
        "position": extract_position(cleaned),
        "company": extract_company(cleaned),
        "city": extract_city(cleaned),
        "salary": extract_salary(cleaned),
        "work_format": extract_work_format(cleaned),
        "experience": extract_experience(cleaned),
        "url": extract_url(msg_text),
        "text": cleaned[:3000],
        "extracted_skills": json.dumps(extract_skills(cleaned)),
    }

def parse_telegram_channels(channels: List[str] = CHANNELS, limit: int = 200):
    if not TG_API_ID or not TG_API_HASH or not TG_PHONE:
        raise EnvironmentError(
            "Set TG_API_ID, TG_API_HASH, and TG_PHONE in your .env file before running the scraper."
        )

    try:
        from telethon.sync import TelegramClient
    except ImportError:
        raise ImportError("Install telethon: pip install telethon --break-system-packages")

    rows: List[Dict] = []

    with TelegramClient(SESSION_FILE, TG_API_ID, TG_API_HASH) as client:
        client.start(phone=TG_PHONE)
        for channel_url in channels:
            channel_name = channel_url.rstrip("/").split("/")[-1]
            print(f"[TG] Scraping @{channel_name} …")
            try:
                entity = client.get_entity(channel_url)
                for msg in client.iter_messages(entity, limit=limit):
                    if not msg.text:
                        continue
                    if not is_job_post(msg.text):
                        continue
                    msg_url = f"https://t.me/{channel_name}/{msg.id}"
                    date_str = msg.date.strftime("%Y-%m-%d") if msg.date else ""
                    views = getattr(msg, "views", 0) or 0
                    rows.append(parse_message(msg.text, channel_name, msg.id, date_str, views, msg_url))
                print(f"[TG] @{channel_name}: found {len(rows)} job posts so far")
            except Exception as exc:
                print(f"[TG] Error scraping @{channel_name}: {exc}")
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"[TG] Done. {len(rows)} job posts saved to {CSV_PATH}")
    return rows

def import_csv_to_db(path: str = CSV_PATH) -> Dict:
    import csv as _csv

    try:
        import pandas as pd
        df = pd.read_csv(path, encoding="utf-8")
        rows_raw = df.to_dict("records")
    except ImportError:
        with open(path, "r", encoding="utf-8") as f:
            rows_raw = list(_csv.DictReader(f))

    from database import SessionLocal
    from models import TelegramJob

    db = SessionLocal()
    inserted = 0
    skipped = 0

    try:
        for row in rows_raw:
            channel = str(row.get("channel", "")).strip()
            message_id = row.get("message_id")
            try:
                message_id = int(message_id) if message_id else None
            except (ValueError, TypeError):
                message_id = None
            existing = (
                db.query(TelegramJob)
                .filter(TelegramJob.channel == channel, TelegramJob.message_id == message_id)
                .first()
            )
            if existing:
                skipped += 1
                continue

            job = TelegramJob(
                channel=channel,
                message_id=message_id,
                date=str(row.get("date", ""))[:50],
                views=int(row.get("views", 0) or 0),
                telegram_url=str(row.get("telegram_url", ""))[:500],
                position=str(row.get("position", ""))[:255],
                company=str(row.get("company", ""))[:255],
                city=str(row.get("city", ""))[:255],
                salary=str(row.get("salary", ""))[:255],
                work_format=str(row.get("work_format", ""))[:100],
                experience=str(row.get("experience", ""))[:100],
                url=str(row.get("url", ""))[:500],
                text=str(row.get("text", ""))[:3000],
                extracted_skills=str(row.get("extracted_skills", "[]")),
            )
            db.add(job)
            inserted += 1

        db.commit()
    finally:
        db.close()

    print(f"[DB] Import complete: {inserted} inserted, {skipped} skipped (duplicates)")
    return {"inserted": inserted, "skipped": skipped, "total": inserted + skipped}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NexCareer Telegram job scraper")
    parser.add_argument("--import", dest="do_import", action="store_true",
                        help="Import existing CSV into PostgreSQL instead of scraping")
    parser.add_argument("--csv", default=CSV_PATH, help="Path to CSV file")
    parser.add_argument("--limit", type=int, default=200, help="Max messages per channel")
    args = parser.parse_args()

    if args.do_import:
        result = import_csv_to_db(args.csv)
        print(result)
    else:
        parse_telegram_channels(limit=args.limit)
