from decimal import Decimal

from django.test import TestCase

from accounts.models import AppMessage, Role, User, UserRole
from accounts.notifications import notify
from expenses.models import Account, ExpenseClaim
from expenses.services import approve_claim, create_claim, submit_claim


def make_user(username, code=None):
    user = User.objects.create_user(username=username, password="Pass#12345")
    if code:
        UserRole.objects.create(user=user, role=Role.objects.get(code=code))
    return user


class MessageCentreTests(TestCase):
    def setUp(self):
        self.user = make_user("receiver")

    def test_badge_shows_unread_count(self):
        notify(self.user, "First", "Body")
        notify(self.user, "Second", "Body")
        self.client.force_login(self.user)
        response = self.client.get("/")
        self.assertContains(response, "updated-badge")
        self.assertContains(response, "2")

    def test_page_lists_messages_and_marks_read(self):
        message = notify(self.user, "Claim approved", "Your claim was approved")
        self.client.force_login(self.user)
        response = self.client.get("/messages/")
        self.assertContains(response, "Claim approved")
        self.assertContains(response, "Unread")

        response = self.client.post("/messages/", {"message_id": message.pk})
        self.assertEqual(response.status_code, 302)
        message.refresh_from_db()
        self.assertIsNotNone(message.read_at)
        self.assertEqual(self.user.app_messages.filter(read_at__isnull=True).count(), 0)

    def test_cannot_mark_someone_elses_message_read(self):
        other = make_user("other")
        message = notify(other, "Private", "Not yours")
        self.client.force_login(self.user)
        response = self.client.post("/messages/", {"message_id": message.pk})
        self.assertEqual(response.status_code, 404)
        message.refresh_from_db()
        self.assertIsNone(message.read_at)


class DecisionMessageTests(TestCase):
    def test_approval_notifies_the_claimant(self):
        claimant = make_user("claimant")
        approver = make_user("approver", "APPROVER")
        Account.objects.get_or_create(
            code="1000", defaults={"name": "Cash", "kind": Account.ASSET}
        )
        Account.objects.get_or_create(
            code="5100", defaults={"name": "Tuition", "kind": Account.EXPENSE}
        )
        claim = create_claim(
            claimant,
            reference="CLM-MSG",
            description="Fees",
            category=ExpenseClaim.TUITION,
            amount=Decimal("4000.00"),
        )
        submit_claim(claimant, claim)
        approve_claim(approver, claim, note="checked")

        message = AppMessage.objects.get(recipient=claimant)
        self.assertIn("CLM-MSG", message.subject)
        self.assertEqual(message.kind, AppMessage.SUCCESS)
        self.assertEqual(message.sender, approver)
