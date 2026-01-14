import joblib
import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity
from matcher.models import Job
import re


# ------- Load Trained Artifacts (TF-IDF Only, Fast) -------
vectorizer = joblib.load("vectorizer.pkl")
job_matrix = joblib.load("job_matrix.pkl")


# ------- Convert DB Jobs to DataFrame -------
jobs_df = pd.DataFrame(list(Job.objects.values()))


# ------- Helper: Parse Skills -------
def _parse_skills(raw_skills: str):
    if not isinstance(raw_skills, str):
        return []
    parts = re.split(r"[,/;]", raw_skills)
    return [p.strip() for p in parts if p.strip()]


# ------- ROLE MATCH ENGINE (TF-IDF) -------
def match_resume(resume_text, top_k=5):
    resume_text = resume_text or ""
    resume_lower = resume_text.lower()

    # Vectorize resume
    resume_vec = vectorizer.transform([resume_text])
    similarities = cosine_similarity(resume_vec, job_matrix)[0]

    # Get top K jobs
    top_indices = similarities.argsort()[::-1][:top_k]

    results = []
    for idx in top_indices:
        row = jobs_df.iloc[idx]

        it_skills_raw = row.get("it_skills", "")

        # Skill gap check
        all_skills = _parse_skills(it_skills_raw)
        matched = [s for s in all_skills if s.lower() in resume_lower]
        missing = [s for s in all_skills if s.lower() not in resume_lower]

        results.append({
            "job_title": row.get("title"),
            "job_description": row.get("description"),
            "it_skills": it_skills_raw,
            "experience": row.get("experience"),
            "matched_skills": matched,
            "missing_skills": missing,
            "score": round(float(similarities[idx] * 100), 2),
        })

    return results


# ------- Get List of Roles for Dropdown -------
def get_all_job_titles():
    return sorted(Job.objects.values_list("title", flat=True).distinct())


# ------- Eligibility Checker (TF-IDF) -------
def check_resume_for_job(resume_text, job_title):
    resume_text = resume_text or ""
    resume_lower = resume_text.lower()

    # Filter dataset for selected title
    subset_df = jobs_df[jobs_df["title"] == job_title]

    if subset_df.empty:
        return None

    resume_vec = vectorizer.transform([resume_text])
    subset_matrix = job_matrix[subset_df.index]

    similarities = cosine_similarity(resume_vec, subset_matrix)[0]
    best_index = similarities.argmax()
    best_row = subset_df.iloc[best_index]
    best_score = similarities[best_index]

    it_skills_raw = best_row.get("it_skills", "")
    all_skills = _parse_skills(it_skills_raw)
    matched = [s for s in all_skills if s.lower() in resume_lower]
    missing = [s for s in all_skills if s.lower() not in resume_lower]

    return {
        "job_title": best_row.get("title"),
        "job_description": best_row.get("description"),
        "it_skills": it_skills_raw,
        "experience": best_row.get("experience"),
        "matched_skills": matched,
        "missing_skills": missing,
        "score": round(float(best_score * 100), 2),
    }
