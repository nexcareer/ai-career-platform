import io
import re
from typing import List
import PyPDF2

try:
    from docx import Document
except ImportError:
    Document = None
ALL_SKILLS = [
    "python", "javascript", "typescript", "java", "c++", "c#", "go", "golang",
    "rust", "kotlin", "swift", "php", "ruby", "scala", "r",
    "react", "vue", "angular", "nextjs", "nuxt", "svelte",
    "fastapi", "django", "flask", "spring", "express", "nestjs",
    "pandas", "numpy", "matplotlib", "seaborn", "scipy",
    "adobe photoshop", "adobe illustrator", "adobe after effects", "adobe premiere pro",
    "corel draw", "coreldraw", "after effects", "premiere pro", "final cut pro", "davinci resolve",
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
COURSE_TO_SKILLS: dict[str, list[str]] = {
    "fundamentals of programming":      ["python", "algorithms", "programming"],
    "programming technologies":         ["python", "programming", "software development"],
    "introduction to algorithms":       ["algorithms", "data structures", "problem solving"],
    "software architecture":            ["software architecture", "design patterns", "oop"],
    "design patterns":                  ["design patterns", "oop", "software architecture"],
    "python for data analysis":         ["python", "pandas", "numpy", "data analysis"],
    "data analysis":                    ["data analysis", "statistics", "python", "pandas"],
    "data visuali":                     ["data visualization", "matplotlib", "tableau"],
    "database management":              ["sql", "database", "postgresql"],
    "databases":                        ["sql", "database", "postgresql"],
    "machine learning":                 ["machine learning", "scikit-learn", "python", "statistics"],
    "deep learning":                    ["deep learning", "tensorflow", "pytorch", "neural networks"],
    "natural language processing":      ["nlp", "machine learning", "python", "text processing"],
    "nlp":                              ["nlp", "machine learning", "python"],
    "discrete mathematics":             ["discrete mathematics", "logic", "algorithms"],
    "linear algebra":                   ["linear algebra", "mathematics"],
    "mathematics for information":      ["mathematics", "applied math"],
    "probability and mathematical":     ["statistics", "probability", "data analysis"],
    "probability":                      ["probability", "statistics"],
    "operating systems":                ["linux", "operating systems", "bash"],
    "computer networks":                ["networking", "tcp/ip", "computer networks"],
    "information security":             ["information security", "cybersecurity", "networking"],
    "information and communication":    ["ict", "technology literacy"],
    "project management":               ["project management", "agile", "scrum"],
    "introduction to business":         ["business analysis", "product management"],
    "financial literacy":               ["financial analysis", "business"],
    "industrial practice":              ["work experience", "professional skills"],
    "english":                          ["english", "technical writing"],
    "foreign language":                 ["english", "communication"],
}
MIN_SCORE_TO_COUNT = 60


def extract_text_from_pdf(file_bytes: bytes) -> str:
    try:
        reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
        text = ""
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n"
        return text
    except Exception:
        return ""


def extract_text_from_docx(file_bytes: bytes) -> str:
    if Document is None:
        return ""
    try:
        doc = Document(io.BytesIO(file_bytes))
        return "\n".join(p.text for p in doc.paragraphs).strip()
    except Exception:
        return ""


def extract_text_from_file(filename: str, file_bytes: bytes) -> str:
    name = filename.lower()
    if name.endswith(".pdf"):
        return extract_text_from_pdf(file_bytes)
    if name.endswith(".docx"):
        return extract_text_from_docx(file_bytes)
    return ""


def _is_transcript(text: str) -> bool:
    indicators = [
        "course code", "course title", "credit", "ects", "grade",
        "gpa", "semester", "letter grade", "transcript",
        "sa :", "ga :", "spa :", "gpa :",
        "pass", "in progress", "excellent",
    ]
    text_lower = text.lower()
    matched = sum(1 for ind in indicators if ind in text_lower)
    return matched >= 3


def _extract_courses_from_transcript(text: str) -> list[dict]:
    courses = []
    pattern = re.compile(
        r'([A-Z]{2,4}\s\d{3})\s+(.+?)\s+(\d+)\s+\d+\s+(\d{1,3}|0)\s+([A-Z][+\-]?|P|NP|IP)',
        re.MULTILINE
    )

    for m in pattern.finditer(text.upper()):
        code      = m.group(1).strip()
        title_raw = m.group(2).strip().title()
        score_raw = m.group(4)
        grade     = m.group(5).strip()
        score = None
        if score_raw.isdigit() and grade not in ("P", "NP"):
            score = int(score_raw)
        elif grade == "P":
            score = 70

        courses.append({
            "code":  code,
            "title": title_raw,
            "score": score,
            "grade": grade,
        })

    return courses


def _skills_from_courses(courses: list[dict]) -> list[str]:
    skills_set: set[str] = set()

    for course in courses:
        score = course.get("score")
        if score is not None and score < MIN_SCORE_TO_COUNT:
            continue

        title_lower = course["title"].lower()

        for keyword, mapped_skills in COURSE_TO_SKILLS.items():
            if keyword in title_lower:
                skills_set.update(mapped_skills)
                break

    return sorted(skills_set)


def _skills_from_plain_text(text: str) -> list[str]:
    text_lower = text.lower()
    found = []
    for skill in ALL_SKILLS:
        if skill in text_lower and skill not in found:
            found.append(skill)
    return found


def extract_skills_from_text(text: str) -> list[str]:
    if not text or not text.strip():
        return []

    if _is_transcript(text):
        courses = _extract_courses_from_transcript(text)
        skills = _skills_from_courses(courses)
        extra = _skills_from_plain_text(text.lower())
        combined = list(set(skills + extra))
        return sorted(combined)
    else:
        return _skills_from_plain_text(text.lower())


def extract_skills_from_transcript_pdf(file_bytes: bytes) -> dict:
    raw_text = extract_text_from_pdf(file_bytes)
    if not raw_text:
        return {"skills": [], "courses": [], "is_transcript": False}

    is_transcript = _is_transcript(raw_text)
    courses = _extract_courses_from_transcript(raw_text) if is_transcript else []
    skills = extract_skills_from_text(raw_text)

    return {
        "skills":        skills,
        "courses":       courses,
        "is_transcript": is_transcript,
        "raw_text":      raw_text,
    }
