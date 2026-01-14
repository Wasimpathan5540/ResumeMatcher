from django.db import models
from django.contrib.auth.models import AnonymousUser



class Job(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField()
    it_skills = models.TextField(blank=True, null=True)
    soft_skills = models.TextField(blank=True, null=True)
    education = models.CharField(max_length=255, blank=True, null=True)
    experience = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return self.title


class MatchHistory(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True)
    input_type = models.CharField(max_length=100)  # General Match / AI Role Suggestion / Job Eligibility Check
    resume_preview = models.TextField(blank=True, null=True)  # first 200 chars
    resume_full = models.TextField(blank=True, null=True)     # full resume / skills text
    role = models.CharField(max_length=255, blank=True, null=True)
    score = models.FloatField(null=True, blank=True)

    # extra fields for analysis
    matched_skills = models.TextField(blank=True, null=True)   # comma-separated
    missing_skills = models.TextField(blank=True, null=True)   # comma-separated

    def __str__(self):
        return f"{self.input_type} -> {self.role} ({self.score}%)"
