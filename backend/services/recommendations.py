from typing import List, Dict

ROLE_SKILL_MAP = {
    "data analyst": ["sql", "python", "pandas", "excel", "power bi", "tableau", "statistics"],
    "backend developer": ["python", "fastapi", "postgresql", "docker", "git", "rest api"],
    "frontend developer": ["javascript", "react", "typescript", "html", "css", "git"],
    "ml engineer": ["python", "tensorflow", "pytorch", "scikit-learn", "sql", "docker", "statistics"],
    "devops engineer": ["docker", "kubernetes", "aws", "terraform", "linux", "bash", "ci/cd"],
    "data scientist": ["python", "pandas", "numpy", "scikit-learn", "statistics", "sql", "machine learning"],
    "fullstack developer": ["javascript", "react", "python", "fastapi", "postgresql", "docker", "git"],
}

SKILL_LEARNING_MAP = {
    "sql": ["Complete SQL Basics course", "Practice queries on SQLZoo", "Build a simple database project"],
    "python": ["Python for Everybody (Coursera)", "Practice on HackerRank", "Build a data analysis mini-project"],
    "pandas": ["Pandas documentation tutorial", "Kaggle Pandas course", "Analyze a real dataset"],
    "power bi": ["Microsoft Power BI free course", "Create a sales dashboard", "Connect to a data source"],
    "tableau": ["Tableau Public tutorials", "Build a visualization project", "Publish to Tableau Public"],
    "docker": ["Docker Get Started tutorial", "Containerize a sample app", "Learn docker-compose"],
    "react": ["React official tutorial", "Build a Todo app", "Add routing with React Router"],
    "machine learning": ["Coursera ML Specialization", "Implement algorithms from scratch", "Kaggle competitions"],
    "postgresql": ["PostgreSQL official tutorial", "Practice on db-fiddle.com", "Design a relational schema"],
    "git": ["Git official documentation", "Practice branching on learngitbranching.js.org", "Contribute to open source"],
    "aws": ["AWS Cloud Practitioner free course", "Deploy a simple app", "Learn S3 and EC2 basics"],
    "kubernetes": ["Kubernetes basics tutorial", "Set up a local cluster with minikube", "Deploy a microservice"],
    "typescript": ["TypeScript handbook", "Convert a JavaScript project", "Build a typed API client"],
    "fastapi": ["FastAPI official tutorial", "Build a CRUD API", "Add authentication and docs"],
    "statistics": ["Statistics with Python (edX)", "Khan Academy Statistics", "Apply stats to a real dataset"],
}

DEFAULT_ROLES = {
    "student": ["data analyst", "backend developer", "frontend developer"],
    "professional": ["ml engineer", "fullstack developer", "devops engineer"],
}


def recommend_roles(skills: List[str], user_role: str = "student") -> List[str]:
    if not skills:
        return DEFAULT_ROLES.get(user_role, ["data analyst", "backend developer"])

    scores = {}
    for role, required in ROLE_SKILL_MAP.items():
        matched = len([s for s in skills if s in required])
        scores[role] = matched

    sorted_roles = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [r for r, _ in sorted_roles[:3] if scores[r] > 0] or list(ROLE_SKILL_MAP.keys())[:3]


def generate_roadmap(missing_skills: List[str], target_role: str = "") -> List[Dict]:
    roadmap = []
    priority_skills = missing_skills[:6]

    if not priority_skills and target_role:
        role_lower = target_role.lower()
        for role, skills in ROLE_SKILL_MAP.items():
            if role in role_lower or role_lower in role:
                priority_skills = skills[:4]
                break

    if not priority_skills:
        priority_skills = ["python", "sql", "git"]

    for skill in priority_skills:
        steps = SKILL_LEARNING_MAP.get(skill, [
            f"Search '{skill}' on Coursera or edX",
            f"Build a small project using {skill}",
            f"Add {skill} to your portfolio",
        ])
        roadmap.append({"skill": skill, "steps": steps})

    return roadmap


def calculate_readiness_score(skills: List[str], target_role: str = "") -> float:
    if not skills:
        return 0.0

    role_lower = target_role.lower() if target_role else ""
    best_match = 0.0

    for role, required in ROLE_SKILL_MAP.items():
        if not role_lower or role in role_lower or role_lower in role:
            matched = len([s for s in skills if s in required])
            score = round(matched / len(required) * 100, 1)
            if score > best_match:
                best_match = score

    if best_match == 0.0:
        best_match = min(len(skills) * 8, 75)

    return best_match
