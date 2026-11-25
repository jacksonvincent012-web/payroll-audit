from django import forms

from accounts.models import SUSResponse, UATParticipant

SUS_QUESTIONS = (
    "I think that I would like to use this system frequently.",
    "I found the system unnecessarily complex.",
    "I thought the system was easy to use.",
    "I think that I would need the support of a technical person to use this system.",
    "I found the various functions in this system were well integrated.",
    "I thought there was too much inconsistency in this system.",
    "I would imagine that most people would learn to use this system very quickly.",
    "I found the system very cumbersome to use.",
    "I felt very confident using the system.",
    "I needed to learn a lot of things before I could get going with this system.",
)

LIKERT = (
    (1, "1 - Strongly disagree"),
    (2, "2 - Disagree"),
    (3, "3 - Neutral"),
    (4, "4 - Agree"),
    (5, "5 - Strongly agree"),
)


class ParticipantForm(forms.ModelForm):
    class Meta:
        model = UATParticipant
        fields = ["code", "role_tested"]


class SUSForm(forms.ModelForm):
    class Meta:
        model = SUSResponse
        fields = [f"q{i}" for i in range(1, 11)] + ["comment"]
        widgets = {
            f"q{i}": forms.Select(choices=LIKERT) for i in range(1, 11)
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for index, question in enumerate(SUS_QUESTIONS, start=1):
            self.fields[f"q{index}"].label = f"{index}. {question}"
        self.fields["comment"].label = "One comment about the task you just performed"
