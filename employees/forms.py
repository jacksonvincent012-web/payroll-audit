from django import forms

from employees.models import Employee

INPUT = "updated-input"


class AttendanceUploadForm(forms.Form):
    csv_file = forms.FileField(label="Attendance CSV")


class PayrollUploadForm(forms.Form):
    period = forms.CharField(max_length=7, help_text="YYYY-MM")
    csv_file = forms.FileField(label="Payroll CSV")


MAX_VIDEO_BYTES = 20 * 1024 * 1024
VIDEO_EXTENSIONS = (".mp4", ".webm", ".mov")


class EmployeeForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = [
            "staff_no",
            "first_name",
            "last_name",
            "national_id",
            "department",
            "job_title",
            "gross_salary",
            "bank_account",
            "phone",
            "is_active",
            "video",
        ]
        widgets = {"gross_salary": forms.NumberInput(attrs={"step": "0.01"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", INPUT)
        if self.instance.pk:
            self.fields["staff_no"].disabled = True

    def clean_video(self):
        video = self.cleaned_data.get("video")
        if not video:
            return video

        name = (video.name or "").lower()
        if not name.endswith(VIDEO_EXTENSIONS):
            raise forms.ValidationError(
                "Verification video must be an mp4, webm or mov file."
            )

        content_type = (getattr(video, "content_type", "") or "").split(";")[0].lower()
        if content_type and not content_type.startswith("video/"):
            raise forms.ValidationError(
                "The uploaded file does not have a video content type."
            )

        if video.size > MAX_VIDEO_BYTES:
            raise forms.ValidationError(
                "Verification video must be 20 MB or smaller."
            )
        return video