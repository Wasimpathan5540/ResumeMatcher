# matcher/career_engine.py

from functools import lru_cache
from pathlib import Path
import csv

from django.conf import settings


CSV_PATH = Path(settings.BASE_DIR) / "jobs.csv"  # your CSV already exists at project root


@lru_cache(maxsize=1)
def load_jobs():
    """
    Load jobs from CSV once and cache them.
    Expected columns:
      - Job Title
      - Description
      - IT Skills
    """
    jobs = []

    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            title = (row.get("Job Title") or "").strip()
            desc = (row.get("Description") or "").strip()
            it_skills = (row.get("IT Skills") or "").strip()

            if not title or not it_skills:
                continue

            jobs.append(
                {
                    "job_title": title,
                    "job_description": desc,
                    "it_skills": it_skills,
                }
            )

    return jobs


@lru_cache(maxsize=1)
def get_all_skills():
    """
    Collect a unique list of skills from the IT Skills column.
    """
    skills = set()
    for job in load_jobs():
        for s in job["it_skills"].split(","):
            s = s.strip()
            if s:
                skills.add(s)
    return sorted(skills)


def extract_skills_from_text(text: str):
    """
    Basic NLP-style skill extraction:
    check which known IT skills appear in the user text.
    """
    text_lower = (text or "").lower()
    found = set()

    for skill in get_all_skills():
        if not skill:
            continue
        if skill.lower() in text_lower:
            found.add(skill)

    return found


def compute_role_suggestions(user_text: str, top_k: int = 5):
    """
    Main engine:
      - extract skills from user_text
      - compare with each job's IT Skills
      - compute match % + present/missing skill lists
    Returns a list of dicts matching what the template expects.
    """
    resume_skills = extract_skills_from_text(user_text)
    jobs = load_jobs()
    results = []

    for job in jobs:
        it_skill_set = {
            s.strip()
            for s in job["it_skills"].split(",")
            if s.strip()
        }

        if not it_skill_set:
            continue

        present = sorted(it_skill_set.intersection(resume_skills))
        missing = sorted(it_skill_set - resume_skills)

        score = (len(present) / len(it_skill_set)) * 100

        results.append(
            {
                "job_title": job["job_title"],
                "job_description": job["job_description"],
                "it_skills": job["it_skills"],
                "score": round(score, 2),
                "present_skills": present,
                "missing_skills": missing,
            }
        )

    # if there are duplicate job titles, keep the best score per title
    dedup = {}
    for r in results:
        title = r["job_title"]
        if title not in dedup or r["score"] > dedup[title]["score"]:
            dedup[title] = r

    sorted_list = sorted(dedup.values(), key=lambda x: x["score"], reverse=True)
    return sorted_list[:top_k]
