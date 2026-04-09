# NexCareer — AI-Driven Career Intelligence Platform

## Overview

**NexCareer** is an intelligent platform for resume analysis and job matching, utilizing AI to match candidate skills with current market requirements.

### Key Features

-  **AI Resume Parsing** — Automatic skill extraction from PDF files
-  **Smart Matching** — Match user profile with jobs via HeadHunter API
-  **Secure Auth** — JWT authorization and bcrypt password hashing
-  **Market Analytics** — Analysis of in-demand skills in the job market
-  **Modern UI** — Futuristic interface with Syne & DM Sans typography

---

##  Technology Stack

### Backend
- **Framework**: FastAPI 0.104.1
- **Server**: Uvicorn 0.24.0
- **Database**: SQLite + SQLAlchemy 2.0.23
- **Auth**: JWT (python-jose) + Bcrypt
- **PDF**: PyPDF2 3.0.1
- **API**: HeadHunter Vacancies

### Frontend
- **HTML5** / **CSS3** / **Vanilla JavaScript**
- **Typography**: Syne Bold, DM Sans Regular
- **Features**: Responsive Design, Real-time Search

---

##  Project Structure

```
NexCareer/
├── backend/
│   ├── main.py               # FastAPI application (628 lines)
│   ├── requirements.txt       # Python dependencies
│   └── NexCareer.db          # SQLite database (462 vacancies)
├── frontend/
│   ├── index.html            # Landing page
│   ├── login.html            # Login
│   ├── register.html         # Registration
│   ├── dashboard.html        # User dashboard
│   └── GUIDE.md              # Documentation
├── .gitignore
└── README.md
```

---

##  Quick Start


###  Install Dependencies

```bash
pip install -r requirements.txt

# If bcrypt error:
pip install bcrypt==4.0.1 passlib
```

### Run Backend

```bash
python main.py
```

**Result**: API running on `http://127.0.0.1:8000`

### Run Frontend (second terminal)

```bash
cd ../frontend
python -m http.server 5500
```

**Result**: Frontend available at `http://127.0.0.1:5500`

---

## API Endpoints

###  Authentication
- `POST /auth/register` — User registration
- `POST /auth/login` — Login
- `GET /auth/me` — Get current user

###  CV Management
- `POST /cv/upload` — Upload and analyze CV (PDF)
- `GET /cv/history` — CV upload history
- `GET /cv/{record_id}` — Get CV data by ID

###  Jobs
- `GET /jobs` — Search jobs with `query` parameter
- `GET /jobs/dataset` — Search local dataset
- `POST /jobs/match` — Match CV with jobs

### Analytics
- `GET /analytics/market-skills` — Top required skills
- `GET /analytics/dashboard` — User dashboard
- `GET /analytics/dataset-stats` — Dataset statistics

###  Health
- `GET /` — API status
- `GET /health` — Health check
- `GET /docs` — Swagger UI documentation

---

##  Local Job Dataset

Project includes **462 vacancies** from HeadHunter API, saved in JSON:
- `hh_kz_vacancies_20260409_230659.json`
- `hh_kz_vacancies_20260409_231007.json`

**Usage**:
- If HeadHunter API unavailable → automatic fallback to local dataset
- Search works on fields: title, requirements, responsibilities, skills

---

##  Security

**JWT Tokens** — 24-hour expiration
**Bcrypt Hashing** — passwords stored securely
**CORS** — requests allowed from `127.0.0.1:5500`
**SQL Injection Protection** — using SQLAlchemy ORM

---

## Data Models

### User
```python
- id (Primary Key)
- email (Unique)
- name
- role (student/professional/employer)
- hashed_password
- created_at (Timestamp)
```

### CVRecord
```python
- id (Primary Key)
- user_id (Foreign Key)
- filename
- raw_text (PDF text)
- extracted_skills (JSON list)
- created_at (Timestamp)
```

### MatchResult
```python
- id (Primary Key)
- user_id (Foreign Key)
- cv_record_id
- job_query
- results_json (JSON results)
- created_at (Timestamp)
```

---

## Skill Extraction

Supported skills (100+):

**Programming Languages**: Python, JavaScript, TypeScript, Java, C++, C#, Go, Rust, PHP, Ruby...

**Frameworks**: React, Vue, Angular, FastAPI, Django, Flask, Express, NestJS...

**Databases**: PostgreSQL, MySQL, SQLite, MongoDB, Redis, Elasticsearch...

**DevOps**: Docker, Kubernetes, AWS, Azure, GCP, Terraform, Jenkins, CI/CD...

**Analytics**: Pandas, NumPy, Matplotlib, Power BI, Tableau, Spark...

---

##  API Testing

### Via Swagger UI
```
http://127.0.0.1:8000/docs
```

### Via cURL
```bash
# Registration
curl -X POST "http://127.0.0.1:8000/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"email":"user@test.com", "password":"pass123", "name":"John", "role":"student"}'

# Login
curl -X POST "http://127.0.0.1:8000/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=user@test.com&password=pass123"

# Search jobs
curl -X GET "http://127.0.0.1:8000/jobs?query=python&per_page=10" \
  -H "Authorization: Bearer YOUR_TOKEN"
```




**🎉 Thank you for using NexCareer!**
