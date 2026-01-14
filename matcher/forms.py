from django import forms


class MatchForm(forms.Form):
    """Home page – general matching with ONLY file upload."""

    resume_file = forms.FileField(
        label="Upload Resume (PDF / DOCX / TXT)",
        required=True,
        widget=forms.ClearableFileInput(
            attrs={
                "class": "form-control",
            }
        ),
    )


class RoleSuggestionForm(forms.Form):
    """AI style page – user just describes skills & interests."""
    skills_text = forms.CharField(
        label="Describe your skills, technologies and interests",
        required=True,
        widget=forms.Textarea(
            attrs={
                "rows": 8,
                "placeholder": "Example: Python, Django, REST APIs, MySQL, basic cloud, data analysis...",
            }
        ),
    )


class RoleCheckForm(forms.Form):
    """Job Check page – select a role + upload/paste resume."""
    job_title = forms.ChoiceField(label="Select Job Role")

    resume_text = forms.CharField(
        label="Resume Text",
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 8,
                "placeholder": "Paste your resume here (or upload a file)...",
            }
        ),
    )
    resume_file = forms.FileField(
        label="Upload Resume (PDF / DOCX / TXT)",
        required=False,
    )

    def __init__(self, *args, **kwargs):
        job_choices = kwargs.pop("job_choices", [])
        super().__init__(*args, **kwargs)
        self.fields["job_title"].choices = [(j, j) for j in job_choices]
