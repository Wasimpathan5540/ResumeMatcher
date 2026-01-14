from django.core.management.base import BaseCommand
import pandas as pd
from matcher.models import Job


class Command(BaseCommand):
    help = "Import jobs from Kaggle CSV into Django database"

    def handle(self, *args, **kwargs):
        df = pd.read_csv("jobs.csv")  # file must be in project root

        for _, row in df.iterrows():
            Job.objects.create(
                title=row.get("Job Title", ""),
                description=row.get("Description", ""),
                it_skills=row.get("IT Skills", ""),
                soft_skills=row.get("Soft Skills", ""),
                education=row.get("Education", ""),
                experience=row.get("Experience", "")
            )

        self.stdout.write(self.style.SUCCESS("Jobs imported successfully 🚀"))
