import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
import joblib

print("📌 Loading dataset...")
df = pd.read_csv("jobs.csv")

# Correct column names from your dataset
TEXT_COL = "Description"      # full job description
TITLE_COL = "Job Title"       # job title
SKILLS_COL = "IT Skills"      # technical required skills

# Remove rows with empty description
df = df.dropna(subset=[TEXT_COL])

# Clean missing text
df[TEXT_COL] = df[TEXT_COL].fillna("")
df[TITLE_COL] = df[TITLE_COL].fillna("Unknown Title")
df[SKILLS_COL] = df[SKILLS_COL].fillna("None")

print("📌 Training TF-IDF Model...")

vectorizer = TfidfVectorizer(stop_words='english')
job_matrix = vectorizer.fit_transform(df[TEXT_COL])

# Save model files
joblib.dump(vectorizer, "vectorizer.pkl")
joblib.dump(job_matrix, "job_matrix.pkl")
df.to_pickle("jobs.pkl")

print("\n🎉 Training Complete!")
print(f"✔ Saved vectorizer.pkl, job_matrix.pkl, jobs.pkl")
print(f"📌 Total job entries used: {len(df)}")
