from django import forms

from employees.models import Employee

INPUT = "updated-input"


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