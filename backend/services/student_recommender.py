import json
import pickle
from pathlib import Path
from typing import Optional

import numpy as np

MODEL_PATH = Path(__file__).resolve().parents[1] / "profession_classifier.pkl"
LEGACY_MODEL_PATH = Path(__file__).parent / "profession_classifier.pkl"
PROFESSION_META: dict[str, dict] = {
    "data scientist":     {"emoji": "🔬", "category": "AI / Data", "color": "#a259ff",
                           "description": "ML-модели, статистика, исследование данных",
                           "key_skills": ["python", "machine learning", "statistics", "pandas", "sql"]},
    "data analyst":       {"emoji": "📊", "category": "Data",       "color": "#00e5c0",
                           "description": "Анализ данных, дашборды, бизнес-инсайты",
                           "key_skills": ["sql", "excel", "python", "tableau", "statistics"]},
    "ml engineer":        {"emoji": "🤖", "category": "AI / ML",   "color": "#5b7fff",
                           "description": "Разработка и деплой ML-систем в продакшн",
                           "key_skills": ["python", "tensorflow", "pytorch", "docker", "mlops"]},
    "data engineer":      {"emoji": "🔧", "category": "Data",       "color": "#ffb347",
                           "description": "ETL-пайплайны, хранилища данных, Spark",
                           "key_skills": ["python", "sql", "spark", "airflow", "postgresql"]},
    "backend developer":  {"emoji": "⚙️",  "category": "Engineering","color": "#5b7fff",
                           "description": "API, серверная логика, базы данных",
                           "key_skills": ["python", "fastapi", "postgresql", "docker", "rest api"]},
    "frontend developer": {"emoji": "🎨", "category": "Engineering","color": "#00e5c0",
                           "description": "UI, веб-интерфейсы, пользовательский опыт",
                           "key_skills": ["javascript", "react", "typescript", "html", "css"]},
    "fullstack developer":{"emoji": "🖥️",  "category": "Engineering","color": "#a259ff",
                           "description": "Полный цикл разработки — от UI до сервера",
                           "key_skills": ["javascript", "react", "python", "postgresql", "docker"]},
    "qa engineer":        {"emoji": "✅", "category": "Quality",    "color": "#00c9a7",
                           "description": "Тестирование, автоматизация, качество продукта",
                           "key_skills": ["selenium", "python", "sql", "postman", "ci/cd"]},
    "devops engineer":    {"emoji": "🛠️",  "category": "Infrastructure","color": "#ffb347",
                           "description": "CI/CD, облака, контейнеры, инфраструктура",
                           "key_skills": ["docker", "kubernetes", "aws", "linux", "terraform"]},
    "mobile developer":   {"emoji": "📱", "category": "Engineering","color": "#ff7eb3",
                           "description": "iOS / Android / кросс-платформенные приложения",
                           "key_skills": ["swift", "kotlin", "react native", "flutter", "mobile"]},
    "product manager":    {"emoji": "🎯", "category": "Management", "color": "#a259ff",
                           "description": "Управление продуктом, стратегия, роадмап",
                           "key_skills": ["product strategy", "analytics", "agile", "scrum", "jira"]},
    "designer":           {"emoji": "✏️",  "category": "Design",    "color": "#ff7eb3",
                           "description": "UI/UX, прототипирование, пользовательские исследования",
                           "key_skills": ["figma", "ux", "prototyping", "user research", "design systems"]},
    "project manager":    {"emoji": "📋", "category": "Management", "color": "#00e5c0",
                           "description": "Планирование, координация команд, дедлайны",
                           "key_skills": ["agile", "scrum", "jira", "risk management", "communication"]},
    "sales manager":      {"emoji": "💼", "category": "Business",   "color": "#ffb347",
                           "description": "B2B/B2C продажи, работа с клиентами",
                           "key_skills": ["crm", "negotiation", "communication", "b2b", "presentations"]},
    "security engineer":  {"emoji": "🔒", "category": "Security",   "color": "#ff5b5b",
                           "description": "Информационная безопасность, пентест, защита систем",
                           "key_skills": ["security", "networking", "linux", "cryptography", "penetration testing"]},
}
COURSE_SKILL_BOOST: dict[str, list[str]] = {
    "machine learning":          ["ml engineer", "data scientist"],
    "deep learning":             ["ml engineer", "data scientist"],
    "natural language processing":["ml engineer", "data scientist"],
    "nlp":                       ["ml engineer", "data scientist"],
    "python":                    ["data scientist", "backend developer", "ml engineer", "data engineer"],
    "tensorflow":                ["ml engineer", "data scientist"],
    "pytorch":                   ["ml engineer", "data scientist"],
    "statistics":                ["data scientist", "data analyst"],
    "probability":               ["data scientist", "data analyst"],
    "data analysis":             ["data analyst", "data scientist"],
    "pandas":                    ["data scientist", "data analyst", "data engineer"],
    "sql":                       ["data analyst", "data engineer", "backend developer"],
    "postgresql":                ["backend developer", "data engineer"],
    "react":                     ["frontend developer", "fullstack developer"],
    "javascript":                ["frontend developer", "fullstack developer"],
    "typescript":                ["frontend developer", "fullstack developer"],
    "docker":                    ["devops engineer", "backend developer", "ml engineer"],
    "kubernetes":                ["devops engineer"],
    "aws":                       ["devops engineer", "data engineer"],
    "linux":                     ["devops engineer", "security engineer"],
    "information security":      ["security engineer"],
    "algorithms":                ["backend developer", "ml engineer"],
    "software architecture":     ["backend developer", "fullstack developer"],
    "database":                  ["data engineer", "backend developer"],
    "figma":                     ["designer"],
    "agile":                     ["product manager", "project manager"],
}

class StudentProfessionRecommender:
    def __init__(self, pipeline):
        self._pipe = pipeline
        self._classes: list[str] = list(pipeline.classes_)

    @classmethod
    def load(cls, path: Path = MODEL_PATH) -> "StudentProfessionRecommender":
        if not path.exists() and LEGACY_MODEL_PATH.exists():
            path = LEGACY_MODEL_PATH
        if not path.exists():
            raise FileNotFoundError(
                f"Модель не найдена: {path}\n"
                "Сначала обучите: python profession_classifier.py --train telegram_all_posts.csv"
            )
        with open(path, "rb") as f:
            pipe = pickle.load(f)
        return cls(pipe)
    def _build_student_text(
        self,
        skills: list[str],
        courses: list[str],
        career_goal: str = "",
        gpa: Optional[float] = None,
    ) -> str:
        parts = []
        if skills:
            parts.append(" ".join(skills))
            parts.append(" ".join(skills))
        if courses:
            parts.append(" ".join(courses))
        if career_goal:
            parts.append(career_goal.lower())

        return " ".join(parts).lower()

    def _get_boost_scores(
        self,
        skills: list[str],
        courses: list[str],
    ) -> np.ndarray:
        boost = np.zeros(len(self._classes))
        all_terms = [s.lower() for s in skills + courses]

        for term in all_terms:
            for skill_kw, professions in COURSE_SKILL_BOOST.items():
                if skill_kw in term or term in skill_kw:
                    for prof in professions:
                        if prof in self._classes:
                            idx = self._classes.index(prof)
                            boost[idx] += 1.0
        if boost.max() > 0:
            boost = boost / boost.max() * 0.3
        return boost

    def recommend(
        self,
        skills: list[str],
        courses: list[str] = None,
        career_goal: str = "",
        gpa: Optional[float] = None,
        top_n: int = 5,
    ) -> dict:
        courses = courses or []
        text = self._build_student_text(skills, courses, career_goal, gpa)
        raw_scores = self._pipe.decision_function([text])[0]
        boost = self._get_boost_scores(skills, courses)
        combined = raw_scores + boost
        top_idx_all = combined.argsort()[::-1]
        exp_s = np.exp(combined - combined.max())
        softmax = exp_s / exp_s.sum()
        if career_goal:
            for i, cls in enumerate(self._classes):
                if cls in career_goal.lower() or career_goal.lower() in cls:
                    combined[i] += 1.5
                    exp_s2 = np.exp(combined - combined.max())
                    softmax = exp_s2 / exp_s2.sum()
                    top_idx_all = combined.argsort()[::-1]
                    break
        recommendations = []
        for rank, idx in enumerate(top_idx_all[:top_n]):
            prof_name = self._classes[idx]
            conf = float(softmax[idx])
            meta = PROFESSION_META.get(prof_name, {
                "emoji": "🎯", "category": "Other", "color": "#7b82a8",
                "description": "", "key_skills": []
            })
            key_skills = meta.get("key_skills", [])
            student_skills_lower = [s.lower() for s in skills]
            matched = [s for s in key_skills if any(s in sk or sk in s for sk in student_skills_lower)]
            missing = [s for s in key_skills if s not in matched]

            match_pct = round(len(matched) / len(key_skills) * 100) if key_skills else 0

            recommendations.append({
                "rank":        rank + 1,
                "profession":  prof_name,
                "emoji":       meta["emoji"],
                "category":    meta["category"],
                "color":       meta["color"],
                "description": meta["description"],
                "confidence":  round(conf * 100, 1),
                "skill_match": match_pct,
                "matched_skills": matched,
                "missing_skills": missing[:4],
                "key_skills":  key_skills,
            })

        top = recommendations[0]
        top_skills_str = ", ".join(skills[:5]) if skills else "не указаны"
        reasoning = self._build_reasoning(top, skills, courses, career_goal)

        return {
            "top_profession":  top,
            "recommendations": recommendations,
            "reasoning":       reasoning,
            "input_skills":    skills,
            "input_courses":   courses,
            "career_goal":     career_goal,
        }

    def _build_reasoning(
        self,
        top: dict,
        skills: list[str],
        courses: list[str],
        career_goal: str,
    ) -> str:
        prof = top["profession"]
        conf = top["confidence"]
        matched = top["matched_skills"]
        missing = top["missing_skills"]

        lines = []
        if conf >= 70:
            lines.append(f"Ваш профиль хорошо соответствует роли **{prof}** ({conf:.0f}% уверенность).")
        elif conf >= 45:
            lines.append(f"Наиболее подходящая роль — **{prof}** ({conf:.0f}%).")
        else:
            lines.append(f"Предварительная рекомендация — **{prof}** (профиль ещё формируется).")

        if matched:
            lines.append(f"Совпадающие навыки: {', '.join(matched)}.")
        if missing:
            lines.append(f"Для усиления позиции изучите: {', '.join(missing)}.")
        if career_goal:
            lines.append(f"Ваша цель «{career_goal}» учтена в анализе.")

        return " ".join(lines)

if __name__ == "__main__":
    print("🎓 NexCareer — Student Profession Recommender\n")

    rec = StudentProfessionRecommender.load()
    result = rec.recommend(
        skills=[
            "python", "machine learning", "natural language processing",
            "statistics", "probability", "data analysis", "algorithms",
            "information security", "software architecture", "linear algebra",
            "deep learning", "data visualisation",
        ],
        courses=[
            "Python for Data Analysis", "Machine Learning",
            "Natural Language Processing", "Deep Learning",
            "Data Analysis", "Probability and Mathematical Statistics",
            "Database Management Systems", "Computer Networks",
            "Information Security", "Software Architecture and Design Patterns",
        ],
        career_goal="ml engineer",
        gpa=3.38,
    )

    print(f"🏆 Top recommendation: {result['top_profession']['emoji']} "
          f"{result['top_profession']['profession'].title()} "
          f"({result['top_profession']['confidence']:.1f}%)\n")

    print("📋 All recommendations:")
    for r in result["recommendations"]:
        bar = "█" * int(r["confidence"] / 5)
        missing = f"  — нужно: {', '.join(r['missing_skills'])}" if r["missing_skills"] else ""
        print(f"  {r['rank']}. {r['emoji']} {r['profession']:<22} {r['confidence']:5.1f}% {bar}{missing}")

    print(f"\n💬 {result['reasoning']}")
