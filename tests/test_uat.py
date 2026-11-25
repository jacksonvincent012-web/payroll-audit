from django.test import TestCase
from django.urls import reverse

from accounts.models import Role, SUSResponse, UATParticipant, User, UserRole


def make_user(username, code=None):
    user = User.objects.create_user(username=username, password="Pass#12345")
    if code:
        UserRole.objects.create(user=user, role=Role.objects.get(code=code))
    return user


def sus_post(**overrides):
    data = {f"q{i}": 3 for i in range(1, 11)}
    data["comment"] = "Clear navigation"
    data.update(overrides)
    return data


class SUSScoringTests(TestCase):
    def setUp(self):
        self.participant = UATParticipant.objects.create(
            code="P01", role_tested="AUDITOR"
        )

    def make_response(self, odd, even):
        values = {
            f"q{i}": (odd if i % 2 else even) for i in range(1, 11)
        }
        return SUSResponse(participant=self.participant, **values)

    def test_neutral_answers_score_fifty(self):
        self.assertEqual(self.make_response(3, 3).score, 50)

    def test_best_answers_score_one_hundred(self):
        self.assertEqual(self.make_response(5, 1).score, 100)

    def test_worst_answers_score_zero(self):
        self.assertEqual(self.make_response(1, 5).score, 0)


class UATFlowTests(TestCase):
    def setUp(self):
        self.user = make_user("tester")
        self.auditor = make_user("auditor", "AUDITOR")
        self.client.force_login(self.user)

    def test_start_page_lists_tasks(self):
        response = self.client.get(reverse("accounts:uat_start"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "User acceptance testing")
        self.assertContains(response, "APPROVER")

    def test_registration_creates_participant_and_redirects(self):
        response = self.client.post(
            reverse("accounts:uat_participant"),
            {"code": "P02", "role_tested": "HR_OFFICER"},
        )
        participant = UATParticipant.objects.get(code="P02")
        self.assertEqual(response.status_code, 302)
        self.assertIn(
            reverse("accounts:uat_sus", args=[participant.pk]), response["Location"]
        )

    def test_submitting_questionnaire_stores_score_and_comment(self):
        participant = UATParticipant.objects.create(
            code="P03", role_tested="AUDITOR"
        )
        response = self.client.post(
            reverse("accounts:uat_sus", args=[participant.pk]),
            sus_post(comment="Easy to find the audit trail"),
        )
        self.assertEqual(response.status_code, 200)
        saved = SUSResponse.objects.get(participant=participant)
        self.assertEqual(saved.score, 50)
        self.assertEqual(saved.comment, "Easy to find the audit trail")
        self.assertContains(response, "50")

    def test_duplicate_submission_is_refused(self):
        participant = UATParticipant.objects.create(
            code="P04", role_tested="ADMIN"
        )
        SUSResponse.objects.create(
            participant=participant, **{f"q{i}": 4 for i in range(1, 11)}
        )
        response = self.client.get(reverse("accounts:uat_sus", args=[participant.pk]))
        self.assertContains(response, "Already submitted")
        self.assertEqual(SUSResponse.objects.count(), 1)

    def test_results_need_auditor_or_admin(self):
        response = self.client.get(reverse("accounts:uat_results"))
        self.assertEqual(response.status_code, 403)

        self.client.force_login(self.auditor)
        response = self.client.get(reverse("accounts:uat_results"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "benchmark 68")
