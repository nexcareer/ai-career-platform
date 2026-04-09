from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from pydantic import BaseModel
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from typing import Optional, List
import os, json, io, requests, glob
import PyPDF2

SECRET_KEY = "nexushire-super-secret-key-2025-capstone"
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24
DATABASE_URL = "sqlite:///./nexushire.db"
HH_API_BASE = "https://api.hh.ru"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    role = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class CVRecord(Base):
    __tablename__ = "cv_records"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False)
    filename = Column(String)
    raw_text = Column(Text)
    extracted_skills = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class MatchResult(Base):
    __tablename__ = "match_results"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False)
    cv_record_id = Column(Integer)
    job_query = Column(String)
    results_json = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


Base.metadata.create_all(bind=engine)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(email: str) -> str:
    expire = datetime.utcnow() + timedelta(hours=TOKEN_EXPIRE_HOURS)
    payload = {"sub": email, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Неверный токен или срок действия истёк",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise credentials_exception
    return user


ALL_SKILLS = [
    "python", "javascript", "typescript", "java", "c++", "c#", "go", "golang",
    "rust", "kotlin", "swift", "php", "ruby", "scala", "r",
    "react", "vue", "angular", "nextjs", "nuxt", "svelte",
    "fastapi", "django", "flask", "spring", "express", "nestjs",
    "pandas", "numpy", "matplotlib", "seaborn", "scipy",
    "tensorflow", "pytorch", "keras", "scikit-learn", "sklearn",
    "postgresql", "postgres", "mysql", "sqlite", "mongodb", "redis",
    "elasticsearch", "cassandra", "oracle", "mssql", "dynamodb",
    "docker", "kubernetes", "k8s", "aws", "azure", "gcp",
    "terraform", "ansible", "jenkins", "github actions", "ci/cd",
    "nginx", "linux", "bash", "shell",
    "sql", "power bi", "tableau", "excel", "looker", "metabase",
    "data analysis", "machine learning", "deep learning",
    "statistics", "probability", "etl", "spark", "hadoop", "airflow",
    "git", "github", "gitlab", "jira", "confluence", "figma",
    "rest api", "graphql", "grpc", "microservices", "websocket",
    "html", "css", "tailwind", "bootstrap", "sass",
    "agile", "scrum", "kanban", "tdd",
    "jwt", "oauth", "api", "swagger",
]


LOCAL_DATASET: List[dict] = []


def load_local_dataset() -> List[dict]:
    all_jobs = []
    base_dir = os.path.dirname(os.path.abspath(__file__))
    search_paths = [
        os.path.join(base_dir, "hh_kz_vacancies_*.json"),
        os.path.join(base_dir, "..", "hh_kz_vacancies_*.json"),
    ]
    json_files = []
    for pattern in search_paths:
        json_files.extend(glob.glob(pattern))
    json_files = sorted(set(os.path.abspath(p) for p in json_files))

    for path in json_files:
        try:
            with open(path, "r", encoding="utf-8") as f:
                items = json.load(f)
                if isinstance(items, list):
                    all_jobs.extend(items)
        except Exception as e:
            print(f"Dataset load error {path}: {e}")
    return all_jobs


def get_local_dataset() -> List[dict]:
    global LOCAL_DATASET
    if not LOCAL_DATASET:
        LOCAL_DATASET = load_local_dataset()
    return LOCAL_DATASET


def format_local_job(item: dict) -> dict:
    salary_from = item.get("salary_from")
    salary_to = item.get("salary_to")
    currency = item.get("currency") or "KZT"
    if salary_from and salary_to:
        salary_str = f"{int(salary_from):,}–{int(salary_to):,} {currency}"
    elif salary_from:
        salary_str = f"от {int(salary_from):,} {currency}"
    elif salary_to:
        salary_str = f"до {int(salary_to):,} {currency}"
    else:
        salary_str = "Не указана"

    return {
        "id": item.get("id", ""),
        "title": item.get("title", ""),
        "company": item.get("company", "Компания"),
        "area": item.get("city", "Казахстан"),
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


def search_local_dataset(query: str, per_page: int = 15) -> List[dict]:
    dataset = get_local_dataset()
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
            item.get("description", "") or "",
        ]).lower()

        score = sum(1 for w in query_words if w in text)
        if score > 0:
            scored.append((score, item))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [format_local_job(item) for _, item in scored[:per_page]]


def extract_text_from_pdf(file_bytes: bytes) -> str:
    try:
        reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
        text = ""
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n"
        return text.lower()
    except Exception as e:
        print(f"PDF extraction error: {e}")
        return ""


def extract_skills_from_text(text: str) -> List[str]:
    text_lower = text.lower()
    found = []
    for skill in ALL_SKILLS:
        if skill in text_lower and skill not in found:
            found.append(skill)
    return found


def calculate_match(cv_skills: List[str], job_description: str) -> dict:
    job_lower = job_description.lower()
    required_skills = [s for s in ALL_SKILLS if s in job_lower]

    if not required_skills:
        matched = cv_skills[:3] if cv_skills else []
        return {
            "score": 50.0,
            "matched": matched,
            "missing": [],
            "required_total": 0
        }

    matched = [s for s in cv_skills if s in required_skills]
    missing = [s for s in required_skills if s not in cv_skills]
    score = round(len(matched) / len(required_skills) * 100, 1)

    return {
        "score": score,
        "matched": matched,
        "missing": missing[:8],
        "required_total": len(required_skills)
    }


def fetch_hh_jobs(query: str, area: int = 160, per_page: int = 15) -> List[dict]:
    try:
        response = requests.get(
            f"{HH_API_BASE}/vacancies",
            params={
                "text": query,
                "area": area,
                "per_page": per_page,
                "order_by": "relevance",
            },
            headers={
                "User-Agent": "NexusHire/1.0-alpha (capstone@sdu.edu.kz)"
            },
            timeout=10
        )

        if response.status_code != 200:
            print(f"HH API error: {response.status_code} — fallback to local dataset")
            return search_local_dataset(query, per_page)

        data = response.json()
        jobs = []

        for item in data.get("items", []):
            salary = item.get("salary")
            salary_str = "Не указана"
            if salary:
                salary_from = salary.get("from")
                salary_to = salary.get("to")
                currency = salary.get("currency", "KZT")
                if salary_from and salary_to:
                    salary_str = f"{salary_from:,}–{salary_to:,} {currency}"
                elif salary_from:
                    salary_str = f"от {salary_from:,} {currency}"
                elif salary_to:
                    salary_str = f"до {salary_to:,} {currency}"

            snippet = item.get("snippet", {})
            requirement = snippet.get("requirement", "") or ""
            responsibility = snippet.get("responsibility", "") or ""

            jobs.append({
                "id": item["id"],
                "title": item["name"],
                "company": item.get("employer", {}).get("name", "Компания"),
                "area": item.get("area", {}).get("name", ""),
                "salary": salary_str,
                "url": item.get("alternate_url", "#"),
                "requirement": requirement.replace("<highlighttext>", "").replace("</highlighttext>", ""),
                "responsibility": responsibility.replace("<highlighttext>", "").replace("</highlighttext>", ""),
                "experience": item.get("experience", {}).get("name", ""),
                "schedule": item.get("schedule", {}).get("name", ""),
                "published": item.get("published_at", "")[:10] if item.get("published_at") else "",
            })

        return jobs

    except requests.Timeout:
        print("HH API timeout — fallback to local dataset")
        return search_local_dataset(query, per_page)
    except Exception as e:
        print(f"HH API exception: {e} — fallback to local dataset")
        return search_local_dataset(query, per_page)


app = FastAPI(
    title="NexusHire API",
    description="AI Career Intelligence Platform — Alpha Build",
    version="1.0.0-alpha"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str
    role: str


class UserResponse(BaseModel):
    id: int
    email: str
    name: str
    role: str

    class Config:
        from_attributes = True


@app.post("/auth/register", tags=["Auth"])
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == req.email).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail="Пользователь с таким email уже существует"
        )

    valid_roles = ["student", "professional", "employer"]
    if req.role not in valid_roles:
        raise HTTPException(status_code=400, detail=f"Роль должна быть одной из: {valid_roles}")

    user = User(
        email=req.email,
        name=req.name,
        role=req.role,
        hashed_password=hash_password(req.password)
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(user.email)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role
        }
    }


@app.post("/auth/login", tags=["Auth"])
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.email == form.username).first()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(
            status_code=401,
            detail="Неверный email или пароль"
        )

    token = create_access_token(user.email)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role
        }
    }


@app.get("/auth/me", tags=["Auth"])
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "name": current_user.name,
        "role": current_user.role,
        "created_at": current_user.created_at.isoformat()
    }


@app.post("/cv/upload", tags=["CV"])
async def upload_cv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Поддерживаются только PDF файлы"
        )

    content = await file.read()

    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Файл пустой")

    text = extract_text_from_pdf(content)
    skills = extract_skills_from_text(text)

    if not text:
        raise HTTPException(
            status_code=422,
            detail="Не удалось извлечь текст из PDF. Убедитесь что PDF не является сканом"
        )

    record = CVRecord(
        user_id=current_user.id,
        filename=file.filename,
        raw_text=text[:5000],
        extracted_skills=json.dumps(skills)
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
        "message": f"Найдено {len(skills)} навыков в вашем CV"
    }


@app.get("/cv/history", tags=["CV"])
def cv_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
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
            "uploaded_at": r.created_at.isoformat()
        }
        for r in records
    ]


@app.get("/cv/{record_id}", tags=["CV"])
def get_cv(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    record = db.query(CVRecord).filter(
        CVRecord.id == record_id,
        CVRecord.user_id == current_user.id
    ).first()

    if not record:
        raise HTTPException(status_code=404, detail="CV не найдено")

    return {
        "id": record.id,
        "filename": record.filename,
        "skills": json.loads(record.extracted_skills) if record.extracted_skills else [],
        "uploaded_at": record.created_at.isoformat()
    }


@app.get("/jobs", tags=["Jobs"])
def get_jobs(
    query: str = "python developer",
    area: int = 160,
    per_page: int = 10,
    current_user: User = Depends(get_current_user)
):
    jobs = fetch_hh_jobs(query, area, per_page)
    source = "local_dataset" if jobs and jobs[0].get("source") == "local_dataset" else "HeadHunter API"
    return {
        "query": query,
        "area": area,
        "total": len(jobs),
        "source": source,
        "jobs": jobs
    }


@app.get("/jobs/dataset", tags=["Jobs"])
def get_dataset_jobs(
    query: str = "python",
    limit: int = 20,
    current_user: User = Depends(get_current_user)
):
    jobs = search_local_dataset(query, per_page=limit)
    return {
        "query": query,
        "source": "local_dataset",
        "total": len(jobs),
        "jobs": jobs
    }


@app.post("/jobs/match", tags=["Jobs"])
async def match_cv_to_jobs(
    file: UploadFile = File(...),
    job_query: str = Form(default="python developer"),
    area: int = Form(default=160),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Только PDF файлы")

    content = await file.read()
    text = extract_text_from_pdf(content)
    cv_skills = extract_skills_from_text(text)

    if not cv_skills:
        cv_skills = ["general skills"]

    jobs = fetch_hh_jobs(job_query, area, per_page=15)

    if not jobs:
        jobs = [
            {
                "id": "demo1", "title": "Python Backend Developer",
                "company": "Kaspi.kz", "area": "Алматы",
                "salary": "600,000–1,000,000 KZT",
                "url": "https://hh.kz", "requirement": "Python, FastAPI, PostgreSQL, Docker, Redis",
                "responsibility": "Разработка backend сервисов",
                "experience": "1–3 года", "schedule": "Полный день", "published": "2026-01-01"
            },
            {
                "id": "demo2", "title": "Data Analyst",
                "company": "Halyk Bank", "area": "Алматы",
                "salary": "400,000–700,000 KZT",
                "url": "https://hh.kz", "requirement": "SQL, Python, Pandas, Excel, Power BI, Tableau",
                "responsibility": "Анализ данных и построение дашбордов",
                "experience": "1–3 года", "schedule": "Удалённая работа", "published": "2026-01-01"
            },
            {
                "id": "demo3", "title": "Frontend Developer",
                "company": "Jusan Bank", "area": "Астана",
                "salary": "500,000–800,000 KZT",
                "url": "https://hh.kz", "requirement": "JavaScript, React, TypeScript, HTML, CSS, Git",
                "responsibility": "Разработка пользовательского интерфейса",
                "experience": "1–3 года", "schedule": "Полный день", "published": "2026-01-01"
            },
        ]

    scored_jobs = []
    for job in jobs:
        job_text = f"{job['title']} {job.get('requirement', '')} {job.get('responsibility', '')} {job.get('key_skills', '')}"
        match = calculate_match(cv_skills, job_text)
        scored_jobs.append({
            **job,
            "match_score": match["score"],
            "matched_skills": match["matched"],
            "missing_skills": match["missing"]
        })

    scored_jobs.sort(key=lambda x: x["match_score"], reverse=True)

    match_record = MatchResult(
        user_id=current_user.id,
        job_query=job_query,
        results_json=json.dumps({"cv_skills": cv_skills, "jobs_count": len(scored_jobs)})
    )
    db.add(match_record)
    db.commit()

    top_match = scored_jobs[0] if scored_jobs else None
    avg_score = round(sum(j["match_score"] for j in scored_jobs) / len(scored_jobs), 1) if scored_jobs else 0

    return {
        "cv_skills": cv_skills,
        "cv_skills_count": len(cv_skills),
        "jobs": scored_jobs,
        "total_jobs": len(scored_jobs),
        "top_match": top_match,
        "average_score": avg_score,
        "query": job_query
    }


@app.get("/analytics/market-skills", tags=["Analytics"])
def market_skills(
    query: str = "python developer",
    current_user: User = Depends(get_current_user)
):
    jobs = fetch_hh_jobs(query, area=160, per_page=20)

    skill_count = {}
    for job in jobs:
        job_text = f"{job.get('requirement', '')} {job.get('responsibility', '')} {job.get('key_skills', '')}"
        found = extract_skills_from_text(job_text)
        for skill in found:
            skill_count[skill] = skill_count.get(skill, 0) + 1

    sorted_skills = sorted(skill_count.items(), key=lambda x: x[1], reverse=True)
    total_jobs = len(jobs) if jobs else 1

    return {
        "query": query,
        "total_jobs_analyzed": len(jobs),
        "top_skills": [
            {
                "skill": skill,
                "count": count,
                "percentage": round(count / total_jobs * 100, 1)
            }
            for skill, count in sorted_skills[:15]
        ]
    }


@app.get("/analytics/dashboard", tags=["Analytics"])
def user_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    cv_records = db.query(CVRecord).filter(CVRecord.user_id == current_user.id).all()
    match_results = db.query(MatchResult).filter(MatchResult.user_id == current_user.id).all()

    all_skills = []
    for r in cv_records:
        if r.extracted_skills:
            all_skills.extend(json.loads(r.extracted_skills))

    unique_skills = list(set(all_skills))

    return {
        "user": {
            "name": current_user.name,
            "email": current_user.email,
            "role": current_user.role
        },
        "stats": {
            "cv_uploaded": len(cv_records),
            "searches_done": len(match_results),
            "skills_found": len(unique_skills),
        },
        "skills": unique_skills,
        "last_cv": {
            "filename": cv_records[-1].filename,
            "skills": json.loads(cv_records[-1].extracted_skills) if cv_records[-1].extracted_skills else [],
            "uploaded_at": cv_records[-1].created_at.isoformat()
        } if cv_records else None
    }


@app.get("/analytics/dataset-stats", tags=["Analytics"])
def dataset_stats(current_user: User = Depends(get_current_user)):
    dataset = get_local_dataset()
    cities = {}
    companies = {}
    queries = {}
    salaries = []

    for item in dataset:
        city = item.get("city", "Unknown")
        cities[city] = cities.get(city, 0) + 1
        comp = item.get("company", "Unknown")
        companies[comp] = companies.get(comp, 0) + 1
        q = item.get("source_query", "other")
        queries[q] = queries.get(q, 0) + 1
        sf = item.get("salary_from")
        if sf:
            try:
                salaries.append(float(sf))
            except:
                pass

    top_cities = sorted(cities.items(), key=lambda x: x[1], reverse=True)[:10]
    top_companies = sorted(companies.items(), key=lambda x: x[1], reverse=True)[:10]

    return {
        "total_vacancies": len(dataset),
        "queries_covered": queries,
        "top_cities": [{"city": c, "count": n} for c, n in top_cities],
        "top_companies": [{"company": c, "count": n} for c, n in top_companies],
        "avg_salary_from": round(sum(salaries) / len(salaries)) if salaries else 0,
        "vacancies_with_salary": len(salaries),
    }


@app.get("/", tags=["Health"])
def root():
    return {
        "status": "ok",
        "app": "NexusHire API",
        "version": "1.0.0-alpha",
        "docs": "/docs",
        "dataset_loaded": len(get_local_dataset()),
        "message": "Добро пожаловать в NexusHire!"
    }


@app.get("/health", tags=["Health"])
def health():
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "dataset_vacancies": len(get_local_dataset())
    }
