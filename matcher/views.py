from django.shortcuts import render
from django.db import models
import csv
from pathlib import Path

from django.conf import settings

from django.shortcuts import render, get_object_or_404
from functools import lru_cache
from django.http import HttpResponse
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,KeepTogether
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from .career_engine import compute_role_suggestions

from .forms import MatchForm, RoleCheckForm, RoleSuggestionForm
from .ml_model import (
    match_resume,
    vectorizer,
    get_all_job_titles,
    check_resume_for_job,
)
from sklearn.metrics.pairwise import cosine_similarity
from PyPDF2 import PdfReader
from docx import Document
from django.contrib.auth.decorators import login_required
from matcher.models import Job, MatchHistory
# ---------- Helpers for job metadata from jobs.csv ----------

CSV_PATH = Path(settings.BASE_DIR) / "jobs.csv"


@lru_cache(maxsize=1)
def get_job_lookup():
    """
    Reads jobs.csv once and builds a lookup:
      title -> { 'description': ..., 'it_skills': ... }
    """
    lookup = {}
    try:
        with open(CSV_PATH, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                title = (row.get("Job Title") or "").strip()
                if not title:
                    continue

                desc = (row.get("Description") or "").strip()
                it_skills = (row.get("IT Skills") or "").strip()

                # if same title appears many times, we just keep the first
                if title not in lookup:
                    lookup[title] = {
                        "description": desc,
                        "it_skills": it_skills,
                    }
    except FileNotFoundError:
        # fail silently – page will still work but without description/skills text
        lookup = {}

    return lookup


def extract_text_from_file(uploaded_file):
    """Read text from TXT / PDF / DOCX without saving to disk."""
    filename = uploaded_file.name.lower()

    if filename.endswith(".txt"):
        return uploaded_file.read().decode("utf-8", errors="ignore")

    if filename.endswith(".pdf"):
        reader = PdfReader(uploaded_file)
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        return text

    if filename.endswith(".docx"):
        doc = Document(uploaded_file)
        paragraphs = [p.text for p in doc.paragraphs]
        return "\n".join(paragraphs)

    raise ValueError("Unsupported file type. Please upload TXT, PDF or DOCX.")


# 1) HOME PAGE – general matching
def home(request):
    dataset_matches = None
    direct_score = None
    error_message = None
    resume_summary = None
    improvement_tips = []
    score_breakdown = None  # NEW

    if request.method == "POST":
        form = MatchForm(request.POST, request.FILES)

        if form.is_valid():
            # only file now
            resume_file = form.cleaned_data.get("resume_file")

            if not resume_file:
                error_message = "Please upload a resume file."
            else:
                try:
                    resume_text = extract_text_from_file(resume_file)
                except Exception as e:
                    resume_text = ""
                    error_message = f"Error reading file: {e}"

                if resume_text and not error_message:
                    # main matching against your jobs DB
                    dataset_matches = match_resume(resume_text, top_k=5)

                    if dataset_matches:
                        top = dataset_matches[0]
                        direct_score = top.get("score", None)

                        matched_skills = top.get("matched_skills", []) or []
                        missing_skills = top.get("missing_skills", []) or []

                        # --------- Simple "AI" Resume Summary ----------
                        total_words = len(resume_text.split())
                        resume_summary = {
                            "suggested_role": top.get("job_title", "Not detected"),
                            "overall_score": direct_score,
                            "word_count": total_words,
                            "matched_skills": matched_skills,
                            "missing_skills": missing_skills[:6],  # top 6 gaps
                        }

                        # --------- Score Breakdown (for bars) ----------
                        total_role_skills = len(matched_skills) + len(missing_skills)
                        if total_role_skills > 0:
                            skills_coverage = (len(matched_skills) / total_role_skills) * 100
                        else:
                            skills_coverage = 0

                        # Ideal resume length ~ 250–700 words
                        if total_words == 0:
                            length_score = 0
                        elif 250 <= total_words <= 700:
                            length_score = 100
                        else:
                            # penalty if too short or too long
                            diff = 0
                            if total_words < 250:
                                diff = 250 - total_words
                            else:
                                diff = total_words - 700
                            length_score = max(40, 100 - (diff / 10))
                        length_score = round(length_score, 1)

                        # Projects score – whether resume mentions projects
                        has_project = "project" in resume_text.lower()
                        projects_score = 100 if has_project else 60

                        score_breakdown = {
                            "skills_coverage": round(skills_coverage, 1),
                            "length_score": length_score,
                            "projects_score": projects_score,
                        }

                        # --------- Improvement Suggestions ----------
                        if missing_skills:
                            improvement_tips.append(
                                "Add the following skills to your resume if you know them or start learning them: "
                                + ", ".join(missing_skills[:6])
                            )

                        if total_words < 150:
                            improvement_tips.append(
                                "Your resume looks very short. Add more details about projects, responsibilities, and achievements."
                            )
                        elif total_words > 800:
                            improvement_tips.append(
                                "Your resume is quite long. Try to keep it concise (1 page for fresher, 2 pages max for experienced)."
                            )

                        if not has_project:
                            improvement_tips.append(
                                "Mention at least 1–2 strong projects with tech stack (e.g., Python, Django, ML, APIs)."
                            )

                        if "django" in resume_text.lower() and "rest" not in resume_text.lower():
                            improvement_tips.append(
                                "You mention Django – also highlight any REST API work (Django REST Framework, API integration) if applicable."
                            )

                        # save history
                        MatchHistory.objects.create(
                            input_type="General Match",
                            resume_preview=resume_text[:200],
                            resume_full=resume_text,
                            role=top.get("job_title", ""),
                            score=top.get("score", 0),
                            matched_skills=",".join(matched_skills),
                            missing_skills=",".join(missing_skills),
                        )
        else:
            error_message = "Please upload a valid resume file."
    else:
        form = MatchForm()

    return render(
        request,
        "matcher/home.html",
        {
            "form": form,
            "dataset_matches": dataset_matches,
            "direct_score": direct_score,
            "error_message": error_message,
            "resume_summary": resume_summary,
            "improvement_tips": improvement_tips,
            "score_breakdown": score_breakdown,   # NEW
        },
    )
# 2) ROLE SUGGESTION PAGE – AI-style skills → roles
# 2) ROLE SUGGESTION PAGE – AI-style skills → roles
def role_suggestion(request):
    suggestions = None
    error_message = None

    if request.method == "POST":
        form = RoleSuggestionForm(request.POST)

        if form.is_valid():
            skills_text = form.cleaned_data["skills_text"] or ""

            if not skills_text.strip():
                error_message = "Please describe your skills and technologies."
            else:
                # Use skills text as "mini resume"
                raw_suggestions = match_resume(skills_text, top_k=5) or []
                job_lookup = get_job_lookup()

                # Build objects in the shape the template expects
                suggestions = []
                for item in raw_suggestions:
                    title = item.get("job_title", "")

                    meta = job_lookup.get(title, {})
                    job_desc = meta.get("description", "")
                    it_skills = meta.get("it_skills", "")

                    suggestions.append(
                        {
                            "job_title": title,
                            "job_description": job_desc,
                            "it_skills": it_skills,
                            "score": round(item.get("score", 0), 2),
                            "present_skills": item.get("matched_skills", []),
                            "missing_skills": item.get("missing_skills", []),
                        }
                    )

                # Save history for this page (if we got at least one suggestion)
                if suggestions:
                    top = suggestions[0]
                    MatchHistory.objects.create(
                        input_type="AI Role Suggestion",
                        resume_preview=skills_text[:200],
                        resume_full=skills_text,
                        role=top["job_title"],
                        score=top["score"],
                        matched_skills=",".join(top.get("present_skills", [])),
                        missing_skills=",".join(top.get("missing_skills", [])),
                    )
        else:
            error_message = "Please fix the errors in the form."
    else:
        form = RoleSuggestionForm()

    return render(
        request,
        "matcher/role_suggestion.html",
        {
            "form": form,
            "suggestions": suggestions,
            "error_message": error_message,
        },
    )

# 3) JOB CHECK PAGE – select job role + resume -> eligibility
def job_check(request):
    job_titles = get_all_job_titles()
    eligibility = None
    error_message = None

    if request.method == "POST":
        form = RoleCheckForm(request.POST, request.FILES, job_choices=job_titles)

        if form.is_valid():
            job_title = form.cleaned_data["job_title"]
            resume_text = form.cleaned_data["resume_text"] or ""
            resume_file = form.cleaned_data["resume_file"]

            if not resume_text and resume_file:
                try:
                    resume_text = extract_text_from_file(resume_file)
                except Exception as e:
                    error_message = f"Error reading file: {e}"

            if not resume_text and not error_message:
                error_message = "Please paste resume text or upload a resume file."
            elif resume_text:
                # Check eligibility for selected job
                eligibility = check_resume_for_job(resume_text, job_title)

                # Save history
                if eligibility:
                    MatchHistory.objects.create(
                        input_type="Job Eligibility Check",
                        resume_preview=resume_text[:200],
                        resume_full=resume_text,
                        role=eligibility["job_title"],
                        score=eligibility["score"],
                        matched_skills=",".join(
                            eligibility.get("matched_skills", [])
                        ),
                        missing_skills=",".join(
                            eligibility.get("missing_skills", [])
                        ),
                    )
                else:
                    # No strong match found – still log the attempt
                    MatchHistory.objects.create(
                        input_type="Job Eligibility Check (No Match)",
                        resume_preview=resume_text[:200],
                        resume_full=resume_text,
                        role=job_title,
                        score=None,
                        matched_skills="",
                        missing_skills="",
                    )
    else:
        form = RoleCheckForm(job_choices=job_titles)

    return render(
        request,
        "matcher/job_check.html",
        {
            "form": form,
            "eligibility": eligibility,
            "error_message": error_message,
        },
    )


# ADMIN DASHBOARD
def dashboard(request):
    job_count = Job.objects.count()          # total jobs in DB
    total_scans = MatchHistory.objects.count()  # total history entries

    # Filter type from query param
    filter_type = request.GET.get("filter", "all")

    history_qs = MatchHistory.objects.all().order_by("-timestamp")

    if filter_type == "general":
        history_qs = history_qs.filter(input_type="General Match")
    elif filter_type == "role":
        history_qs = history_qs.filter(input_type="AI Role Suggestion")
    elif filter_type == "jobcheck":
        history_qs = history_qs.filter(input_type__startswith="Job Eligibility Check")

    avg_score = (
        history_qs.exclude(score__isnull=True).aggregate(models.Avg("score"))[
            "score__avg"
        ]
    )

    return render(
        request,
        "matcher/dashboard.html",
        {
            "job_count": job_count,
            "total_scans": total_scans,
            "history": history_qs[:20],  # latest 20 filtered
            "avg_score": round(avg_score, 2) if avg_score is not None else None,
            "active_filter": filter_type,
        },
    )
# (you already import Job, MatchHistory above)

def history_detail(request, pk):
    record = get_object_or_404(MatchHistory, pk=pk)

    matched = record.matched_skills.split(",") if record.matched_skills else []
    missing = record.missing_skills.split(",") if record.missing_skills else []

    return render(request, "matcher/history_detail.html", {
        "record": record,
        "matched_skills": [s.strip() for s in matched if s.strip()],
        "missing_skills": [s.strip() for s in missing if s.strip()],
    })



def history_pdf(request, pk):
    record = get_object_or_404(MatchHistory, pk=pk)

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="resume_analysis_{pk}.pdf"'

    # 1. Setup Document
    doc = SimpleDocTemplate(
        response,
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40,
    )

    # 2. Define Styles
    styles = getSampleStyleSheet()

    # Custom Colors
    primary_color = colors.HexColor("#4F46E5")  # Indigo
    text_color = colors.HexColor("#1F2937")     # Dark Gray
    light_bg = colors.HexColor("#F9FAFB")       # Very Light Gray
    success_color = colors.HexColor("#059669")  # Green
    warning_color = colors.HexColor("#D97706")  # Amber
    danger_color = colors.HexColor("#DC2626")   # Red

    # Custom Paragraph Styles
    style_title = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=primary_color,
        spaceAfter=10,
        fontName='Helvetica-Bold',
    )

    style_subtitle = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Normal'],
        fontSize=12,
        textColor=colors.gray,
        spaceAfter=30,
    )

    style_section_head = ParagraphStyle(
        'SectionHead',
        parent=styles['Heading3'],
        fontSize=14,
        textColor=text_color,
        spaceAfter=10,
        spaceBefore=20,
        fontName='Helvetica-Bold',
    )

    style_body = ParagraphStyle(
        'Body',
        parent=styles['Normal'],
        fontSize=10,
        textColor=text_color,
        leading=14,
    )

    style_skill_item = ParagraphStyle(
        'SkillItem',
        parent=styles['Normal'],
        fontSize=10,
        leading=14,
        textColor=text_color,
    )

    story = []

    # =============== HEADER SECTION ===============
    gen_date = datetime.now().strftime("%B %d, %Y")

    story.append(Paragraph("Resume Match Analysis", style_title))
    story.append(
        Paragraph(
            f"<b>Target Role:</b> {record.role} &nbsp;|&nbsp; <b>Date:</b> {gen_date}",
            style_subtitle,
        )
    )

    story.append(
        HRFlowable(width="100%", thickness=1, color=colors.lightgrey, spaceAfter=20)
    )

    # =============== SCORE SECTION ===============
    score_val = record.score or 0
    if score_val >= 80:
        s_color = success_color
        s_text = "EXCELLENT MATCH"
    elif score_val >= 60:
        s_color = warning_color
        s_text = "GOOD MATCH"
    else:
        s_color = danger_color
        s_text = "LOW MATCH"

    score_data = [
        [Paragraph(f"<b>{s_text}</b>", style_section_head), f"{score_val}%"]
    ]

    score_table = Table(score_data, colWidths=[350, 150])
    score_table.setStyle(
        TableStyle(
            [
                ('ALIGN', (0, 0), (0, 0), 'LEFT'),
                ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TEXTCOLOR', (1, 0), (1, 0), s_color),
                ('FONTNAME', (1, 0), (1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (1, 0), (1, 0), 32),
            ]
        )
    )

    story.append(score_table)
    story.append(Spacer(1, 20))

    # =============== SKILLS COMPARISON SECTION ===============
    story.append(Paragraph("Skills Analysis", style_section_head))

    matched_list = (
        [f"• {s.strip()}" for s in record.matched_skills.split(",") if s.strip()]
        if record.matched_skills
        else ["None"]
    )
    missing_list = (
        [f"• {s.strip()}" for s in record.missing_skills.split(",") if s.strip()]
        if record.missing_skills
        else ["None"]
    )

    matched_flowable = [Paragraph(item, style_skill_item) for item in matched_list]
    missing_flowable = [Paragraph(item, style_skill_item) for item in missing_list]

    skill_data = [
        [
            Paragraph("<b>MATCHED SKILLS</b>", style_body),
            Paragraph("<b>MISSING SKILLS</b>", style_body),
        ],
        [matched_flowable, missing_flowable],
    ]

    skill_table = Table(skill_data, colWidths=[240, 240])
    skill_table.setStyle(
        TableStyle(
            [
                # Header row
                ('BACKGROUND', (0, 0), (0, 0), colors.HexColor("#DCFCE7")),
                ('BACKGROUND', (1, 0), (1, 0), colors.HexColor("#FEE2E2")),
                ('TEXTCOLOR', (0, 0), (0, 0), colors.HexColor("#166534")),
                ('TEXTCOLOR', (1, 0), (1, 0), colors.HexColor("#991B1B")),
                ('PADDING', (0, 0), (-1, 0), 10),
                # Content
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor("#E5E7EB")),
                ('PADDING', (0, 1), (-1, 1), 10),
            ]
        )
    )

    story.append(skill_table)
    story.append(Spacer(1, 30))

    # =============== RESUME CONTENT SECTION ===============
    story.append(Paragraph("Analyzed Content", style_section_head))
    story.append(Spacer(1, 10))

    resume_text = record.resume_full or record.resume_preview or ""
    resume_lines = resume_text.split("\n")

    # Use KeepTogether for nicer grouping but NOT a table (tables cause LayoutError)
    resume_block = []

    # Add a soft background effect using paragraphs and spacing
    resume_block.append(Paragraph("", style_body))

    for line in resume_lines:
        if line.strip():
            resume_block.append(Paragraph(line.strip(), style_body))
        resume_block.append(Spacer(1, 4))

    story.append(KeepTogether(resume_block))
    story.append(Spacer(1, 30))

    # =============== FOOTER ===============
    story.append(HRFlowable(width="100%", thickness=1, color=colors.lightgrey))
    story.append(Spacer(1, 5))
    story.append(
        Paragraph(
            "Generated by Resume Matcher AI System",
            ParagraphStyle(
                'Footer',
                parent=styles['Normal'],
                fontSize=8,
                textColor=colors.gray,
                alignment=1,
            ),
        )
    )

    doc.build(story)
    return response


