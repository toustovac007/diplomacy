from datetime import timedelta
import json
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch
from unittest import skipUnless

from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from django.test import TransactionTestCase
from django.db import connection, connections
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from . import email_verification as verification
from .models import User, EmailVerification, VerificationRequestLimit

REQUEST = "/api/users/email/verification/request/"
CONFIRM = "/api/users/email/verification/confirm/"


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
                   EMAIL_VERIFICATION_FRONTEND_URL="https://diplomacy.example")
class EmailVerificationTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.password = "Bamboo!river83-moon"
        self.user = User.objects.create_user(username="pending", email="pending@example.test", password=self.password)

    def raw(self):
        url = next(line for line in mail.outbox[-1].body.splitlines() if line.startswith("https://"))
        self.assertEqual(urlsplit(url).netloc, "diplomacy.example")
        self.assertEqual(urlsplit(url).path, "/verify-email")
        self.assertFalse(urlsplit(url).query)
        return parse_qs(urlsplit(url).fragment)["token"][0]

    def test_registration_is_pending_and_does_not_expose_credentials_or_tokens(self):
        response = self.client.post("/api/users/register/", {"username":"new", "email":"NEW@example.test",
            "password":self.password, "email_verified_at":timezone.now().isoformat(), "is_staff":True})
        self.assertEqual(response.status_code, 201)
        user = User.objects.get(username="new")
        self.assertFalse(user.is_email_verified or user.is_staff)
        self.assertTrue(user.check_password(self.password))
        self.assertEqual(user.email, "new@example.test")
        self.assertEqual(list(response.data), ["detail"])
        self.assertEqual(len(mail.outbox), 1)
        raw = self.raw()
        self.assertEqual(EmailVerification.objects.get(user=user).token_digest, verification.digest(raw))
        self.assertNotIn(raw, str(response.data))
        self.assertNotIn(raw, str(list(EmailVerification.objects.values())))
        self.assertEqual(mail.outbox[0].alternatives[0].mimetype, "text/html")

    def test_pending_user_cannot_login_refresh_or_use_old_access_tokens(self):
        response = self.client.post("/api/token/", {"username":self.user.username,"password":self.password})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data["detail"], "email_not_verified")
        pair = RefreshToken.for_user(self.user)
        self.assertEqual(self.client.post("/api/token/refresh/", {"refresh":str(pair)}).status_code, 401)
        self.client.credentials(HTTP_AUTHORIZATION="Bearer "+str(pair.access_token))
        for path in ("/api/users/me/", "/api/games/", "/api/notifications/preferences/"):
            self.assertEqual(self.client.get(path).status_code, 401)
        self.assertEqual(self.client.post("/api/games/", {"name":"spam"}).status_code, 401)

    def test_opening_link_does_not_activate_and_confirmation_is_single_use(self):
        verification.request_verification(self.user.pk)
        raw = self.raw()
        self.assertEqual(self.client.get(CONFIRM, {"token":raw}).status_code, 405)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_email_verified)
        response = self.client.post(CONFIRM, {"token":raw})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"detail":"email_verified"})
        self.assertEqual(response["Cache-Control"], "no-store")
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_email_verified)
        self.assertEqual(self.client.post(CONFIRM, {"token":raw}).status_code, 400)
        self.assertEqual(self.client.post("/api/token/", {"username":self.user.username,"password":self.password}).status_code, 200)

    def test_expired_tampered_unknown_and_malformed_proofs_fail(self):
        verification.request_verification(self.user.pk)
        raw = self.raw()
        for body in ({}, {"token":[]}, {"token":None}, {"token":"x"*129}, {"token":raw+"x"}, []):
            self.assertEqual(self.client.post(CONFIRM, body, format="json").status_code, 400)
        malformed = json.dumps({"token":"\ud800"*43})
        self.assertEqual(self.client.post(CONFIRM, malformed, content_type="application/json").status_code, 400)
        EmailVerification.objects.update(expires_at=timezone.now()-timedelta(seconds=1))
        self.assertEqual(self.client.post(CONFIRM,{"token":raw}).status_code,400)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_email_verified)

    def test_generic_resend_for_unknown_verified_and_pending_addresses(self):
        unknown = self.client.post(REQUEST,{"email":"unknown@example.test"})
        pending = self.client.post(REQUEST,{"email":self.user.email})
        self.assertEqual(unknown.status_code,202)
        self.assertEqual(unknown.data,pending.data)
        verification.mark_verified(self.user)
        verified = self.client.post(REQUEST,{"email":self.user.email})
        self.assertEqual(verified.data,unknown.data)
        self.assertEqual(len(mail.outbox),1)

    def test_existing_email_registration_never_replaces_password_or_activates(self):
        response = self.client.post("/api/users/register/",{"username":"attacker", "email":"PENDING@example.test",
            "password":"Different!password84"})
        self.assertEqual(response.status_code,201)
        self.assertEqual(User.objects.count(),1)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.password))
        self.assertFalse(self.user.is_email_verified)

    def test_resends_have_shared_cooldown_hourly_budget_and_replace_old_token(self):
        start = timezone.now()
        with patch.object(verification.timezone,"now",return_value=start):
            self.assertTrue(verification.request_verification(self.user.pk))
            first = self.raw()
            self.assertFalse(verification.request_verification(self.user.pk))
        for minute in range(1,5):
            with patch.object(verification.timezone,"now",return_value=start+timedelta(minutes=minute)):
                self.assertTrue(verification.request_verification(self.user.pk))
        last = self.raw()
        with patch.object(verification.timezone,"now",return_value=start+timedelta(minutes=6)):
            self.assertFalse(verification.request_verification(self.user.pk))
        self.assertEqual(len(mail.outbox),5)
        self.assertFalse(verification.confirm_verification(first))
        self.assertTrue(verification.confirm_verification(last))

    def test_smtp_failure_is_sanitized_keeps_account_pending_and_is_retryable(self):
        with patch("apps.users.email_verification.EmailMultiAlternatives.send",side_effect=RuntimeError("password=SECRET")):
            with self.assertLogs("apps.users.email_verification",level="ERROR") as logs:
                self.assertEqual(self.client.post(REQUEST,{"email":self.user.email}).status_code,202)
        self.assertNotIn("SECRET"," ".join(logs.output))
        proof = EmailVerification.objects.get(user=self.user)
        self.assertIsNone(proof.token_digest)
        self.assertEqual(proof.send_count,1)
        EmailVerification.objects.update(last_sent_at=timezone.now()-timedelta(minutes=2))
        self.assertTrue(verification.request_verification(self.user.pk))
        self.assertTrue(verification.confirm_verification(self.raw()))

    def test_failed_resend_preserves_previous_working_link(self):
        verification.request_verification(self.user.pk)
        raw = self.raw()
        EmailVerification.objects.update(last_sent_at=timezone.now()-timedelta(minutes=2))
        with patch("apps.users.email_verification.EmailMultiAlternatives.send",return_value=0):
            self.assertFalse(verification.request_verification(self.user.pk))
        self.assertTrue(verification.confirm_verification(raw))

    def test_ip_limits_are_database_backed_and_survive_cache_clear(self):
        for _ in range(20):
            self.assertEqual(self.client.post(REQUEST,{"email":"unknown@example.test"}).status_code,202)
        cache.clear()
        self.assertEqual(self.client.post(REQUEST,{"email":self.user.email}).status_code,429)
        self.assertNotIn("127.0.0.1",str(list(VerificationRequestLimit.objects.values())))

    def test_address_change_invalidates_link_and_previously_issued_jwts(self):
        verification.request_verification(self.user.pk)
        raw = self.raw()
        self.user.email = "changed@example.test"
        self.user.save(update_fields=["email"])
        self.assertFalse(verification.confirm_verification(raw))
        verification.mark_verified(self.user)
        pair = RefreshToken.for_user(self.user)
        self.user.email = "another@example.test"
        self.user.save(update_fields=["email"])
        self.client.credentials(HTTP_AUTHORIZATION="Bearer "+str(pair.access_token))
        self.assertEqual(self.client.get("/api/users/me/").status_code,401)
        self.assertEqual(self.client.post("/api/token/refresh/",{"refresh":str(pair)}).status_code,401)

    def test_disabled_account_cannot_be_activated_by_old_proof(self):
        verification.request_verification(self.user.pk)
        raw = self.raw()
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        self.assertFalse(verification.confirm_verification(raw))
        self.assertFalse(verification.request_verification(self.user.pk))

    def test_restoring_an_old_address_does_not_restore_its_verification_or_link(self):
        verification.request_verification(self.user.pk)
        raw = self.raw()
        original = self.user.email
        self.user.email = "changed@example.test"
        self.user.save(update_fields=["email"])
        self.user.email = original
        self.user.save(update_fields=["email"])
        self.assertFalse(verification.confirm_verification(raw))
        verification.mark_verified(self.user)
        self.user.email = "changed@example.test"
        self.user.save(update_fields=["email"])
        self.user.email = original
        self.user.save(update_fields=["email"])
        self.assertFalse(self.user.is_email_verified)


@skipUnless(connection.vendor == "postgresql", "Requires a live PostgreSQL test database")
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class VerificationConcurrencyTests(TransactionTestCase):
    def parallel(self, action):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        barrier = Barrier(2)
        def run(_):
            try:
                barrier.wait(timeout=10)
                return action()
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(run, range(2)))

    def test_simultaneous_resends_send_one_message(self):
        user = User.objects.create_user(username="parallel",email="parallel@example.test")
        mail.get_connection()
        self.assertEqual(sorted(self.parallel(lambda:verification.request_verification(user.pk))),[False,True])
        self.assertEqual(len(mail.outbox),1)
        self.assertEqual(EmailVerification.objects.get().send_count,1)

    def test_same_confirmation_cannot_be_consumed_twice(self):
        user = User.objects.create_user(username="parallel",email="parallel@example.test")
        verification.request_verification(user.pk)
        raw = parse_qs(urlsplit(next(line for line in mail.outbox[-1].body.splitlines() if '#token=' in line)).fragment)['token'][0]
        self.assertEqual(sorted(self.parallel(lambda:verification.confirm_verification(raw))),[False,True])

    def test_last_ip_slot_cannot_be_spent_twice(self):
        for _ in range(19):
            self.assertTrue(verification.allow_request("same-ip"))
        self.assertEqual(sorted(self.parallel(lambda:verification.allow_request("same-ip"))),[False,True])
