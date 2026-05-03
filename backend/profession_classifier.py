import argparse
import json
import os
import pickle
import re
from pathlib import Path
from typing import Optional

import pandas as pd

MODEL_PATH = Path(__file__).parent / "profession_classifier.pkl"
LABEL_INFO_PATH = Path(__file__).parent / "label_info.json"
LABEL_RULES: dict[str, list[str]] = {
    "data scientist":     ["data scientist", "data science"],
    "data analyst":       ["data analyst", "аналитик данных"],
    "ml engineer":        ["ml engineer", "machine learning engineer"],
    "data engineer":      ["data engineer", "etl разработч"],
    "backend developer":  ["backend developer", "back-end developer", "бэкенд разработ"],
    "frontend developer": ["frontend developer", "front-end developer", "фронтенд разработ"],
    "fullstack developer":["full stack developer", "fullstack developer"],
    "qa engineer":        ["qa engineer", "qa-engineer", "тестировщик"],
    "devops engineer":    ["devops engineer", "devops-engineer", "sre engineer"],
    "mobile developer":   ["ios developer", "android developer", "flutter developer", "react native developer"],
    "product manager":    ["product manager"],
    "designer":           ["ui/ux designer", "ux/ui designer", "product designer"],
    "project manager":    ["project manager"],
    "sales manager":      ["sales manager"],
    "security engineer":  ["security engineer", "cybersecurity engineer"],
}
PROFESSION_META: dict[str, dict] = {
    "data scientist":     {"emoji": "🔬", "category": "Data"},
    "data analyst":       {"emoji": "📊", "category": "Data"},
    "ml engineer":        {"emoji": "🤖", "category": "AI/ML"},
    "data engineer":      {"emoji": "🔧", "category": "Data"},
    "backend developer":  {"emoji": "⚙️",  "category": "Engineering"},
    "frontend developer": {"emoji": "🎨", "category": "Engineering"},
    "fullstack developer":{"emoji": "🖥️",  "category": "Engineering"},
    "qa engineer":        {"emoji": "✅", "category": "Quality"},
    "devops engineer":    {"emoji": "🛠️",  "category": "Infrastructure"},
    "mobile developer":   {"emoji": "📱", "category": "Engineering"},
    "product manager":    {"emoji": "🎯", "category": "Management"},
    "designer":           {"emoji": "✏️",  "category": "Design"},
    "project manager":    {"emoji": "📋", "category": "Management"},
    "sales manager":      {"emoji": "💼", "category": "Sales"},
    "security engineer":  {"emoji": "🔒", "category": "Security"},
}

def clean_text(text: str) -> str:
    text = re.sub(r"http\S+", "", str(text))
    text = re.sub(r"@\S+", "", text)
    text = re.sub(r"#\S+", "", text)
    text = re.sub(r"\*\*|\*|__|`", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text.lower()


def extract_label(text: str) -> Optional[str]:
    t = text.lower() if isinstance(text, str) else ""
    for label, phrases in LABEL_RULES.items():
        for phrase in phrases:
            if phrase in t:
                return label
    return None

def train(csv_path: str, save: bool = True):
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.svm import LinearSVC
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import classification_report, accuracy_score

    print(f"📂 Loading {csv_path}…")
    df = pd.read_csv(csv_path)

    print("🏷  Extracting labels…")
    df["label"] = df["text"].apply(extract_label)
    df["clean"] = df["text"].apply(clean_text)

    df_labeled = df[df["label"].notna()].copy()
    print(f"   Labeled rows: {len(df_labeled)} / {len(df)}")
    print(f"   Class distribution:\n{df_labeled['label'].value_counts().to_string()}\n")

    X = df_labeled["clean"].values
    y = df_labeled["label"].values

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    pipe = Pipeline([
        ("tfidf", TfidfVectorizer(
            max_features=20_000,
            ngram_range=(1, 3),
            sublinear_tf=True,
            analyzer="word",
        )),
        ("clf", LinearSVC(C=1.0, class_weight="balanced", max_iter=2000)),
    ])

    print("⚙️  Training LinearSVC + TF-IDF…")
    pipe.fit(X_train, y_train)

    preds = pipe.predict(X_test)
    acc   = accuracy_score(y_test, preds)
    report = classification_report(y_test, preds, zero_division=0)

    print(f"\n✅ Accuracy: {acc:.4f}")
    print(report)

    if save:
        with open(MODEL_PATH, "wb") as f:
            pickle.dump(pipe, f)

        label_info = {
            "model":        "LinearSVC + TF-IDF (ngram 1-3)",
            "accuracy":     round(acc, 4),
            "total_labeled": int(len(df_labeled)),
            "classes":      df_labeled["label"].value_counts().to_dict(),
            "trained_on":   str(csv_path),
        }
        with open(LABEL_INFO_PATH, "w", encoding="utf-8") as f:
            json.dump(label_info, f, ensure_ascii=False, indent=2)

        print(f"\n💾 Model saved → {MODEL_PATH}")
        print(f"💾 Info  saved → {LABEL_INFO_PATH}")

    return pipe, acc, report

class ProfessionClassifier:
    def __init__(self, pipeline):
        self._pipe = pipeline
        self._has_proba = hasattr(self._pipe.named_steps.get("clf"), "predict_proba")

    @classmethod
    def load(cls, path: Path = MODEL_PATH) -> "ProfessionClassifier":
        if not path.exists():
            raise FileNotFoundError(
                f"Model not found at {path}. "
                "Run: python profession_classifier.py --train telegram_all_posts.csv"
            )
        with open(path, "rb") as f:
            pipe = pickle.load(f)
        return cls(pipe)

    def predict(self, text: str) -> dict:
        cleaned = clean_text(text)
        profession = self._pipe.predict([cleaned])[0]
        meta = PROFESSION_META.get(profession, {"emoji": "🎯", "category": "Other"})

        result = {
            "profession": profession,
            "emoji":      meta["emoji"],
            "category":   meta["category"],
            "confidence": None,
            "top3":       [],
        }

        if self._has_proba:
            proba = self._pipe.predict_proba([cleaned])[0]
            classes = self._pipe.classes_
            top_idx = proba.argsort()[::-1][:3]
            result["confidence"] = round(float(proba[top_idx[0]]), 3)
            result["top3"] = [
                {
                    "profession": classes[i],
                    "confidence": round(float(proba[i]), 3),
                    "emoji": PROFESSION_META.get(classes[i], {}).get("emoji", "🎯"),
                }
                for i in top_idx
            ]

        return result

    def predict_batch(self, texts: list[str]) -> list[dict]:
        return [self.predict(t) for t in texts]
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NexCareer Profession Classifier")
    parser.add_argument("--train", metavar="CSV", help="Path to telegram_all_posts.csv")
    parser.add_argument("--predict", metavar="TEXT", help="Predict profession from text")
    args = parser.parse_args()

    if args.train:
        train(args.train)

    elif args.predict:
        clf = ProfessionClassifier.load()
        result = clf.predict(args.predict)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    else:
        if MODEL_PATH.exists():
            clf = ProfessionClassifier.load()
            samples = [
                "Ищем Senior Python Developer. Требования: FastAPI, PostgreSQL, Docker, REST API.",
                "Data Scientist. Нужен опыт с pandas, scikit-learn, TensorFlow, SQL.",
                "Вакансия: DevOps Engineer. Kubernetes, AWS, Terraform, CI/CD, Linux.",
                "UI/UX Designer. Figma, продуктовый дизайн, A/B тестирование.",
                "QA Engineer — ручное и автотестирование, Selenium, API testing.",
            ]
            print("Demo predictions:\n")
            for s in samples:
                r = clf.predict(s)
                print(f"  {r['emoji']} {r['profession']:<22} «{s[:60]}…»")
        else:
            print("No model found. Run with --train <csv>")
