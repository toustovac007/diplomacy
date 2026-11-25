"""Single-use email proofs. No application session is issued by this flow."""
from datetime import timedelta
import hashlib
import logging
import re
import secrets
from urllib.parse import urlencode

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django.views.decorators.debug import sensitive_variables

from .models import EmailVerification, User, VerificationRequestLimit

logger = logging.getLogger(__name__)
REQUEST_MESSAGE = "Pokud adresa patří účtu čekajícímu na ověření, odešleme na ni potvrzovací e-mail. Zkontrolujte i spam."


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def mark_verified(user):
    user.email_verified_at = timezone.now()
    user.email_verified_for = user.email
    user.save(update_fields=["email_verified_at", "email_verified_for"])


def allow_request(ident, scope="request", limit=20):
    """Database-backed IP budget, shared across workers and restarts."""
    now = timezone.now()
    key = salted_hmac("email-verification", f"{scope}:{ident}", algorithm="sha256").hexdigest()
    with transaction.atomic():
        VerificationRequestLimit.objects.get_or_create(key=key, defaults={"window_start": now})
        bucket = VerificationRequestLimit.objects.select_for_update().get(pk=key)
        if bucket.window_start <= now - timedelta(hours=1):
            bucket.window_start, bucket.count = now, 0
        if bucket.count >= limit:
            return False
        bucket.count += 1
        bucket.save(update_fields=["window_start", "count"])
    return True


@sensitive_variables()
def request_verification(user_id):
    # Serialize creation/resends for this account, including SMTP failures.
    with transaction.atomic():
        user = User.objects.select_for_update().filter(pk=user_id).first()
        if not user or not user.is_active or user.is_email_verified or not user.email:
            return False
        proof, _ = EmailVerification.objects.get_or_create(user=user)
        now = timezone.now()
        if proof.window_start is None or proof.window_start <= now - timedelta(hours=1):
            proof.window_start, proof.send_count = now, 0
        if (proof.last_sent_at and proof.last_sent_at > now - timedelta(seconds=60)) or proof.send_count >= 5:
            return False
        proof.last_sent_at, proof.send_count = now, proof.send_count + 1
        proof.save(update_fields=["last_sent_at", "window_start", "send_count"])
        raw = secrets.token_urlsafe(32)
        # A fragment stays out of proxy/access logs and HTTP Referer headers.
        url = settings.EMAIL_VERIFICATION_FRONTEND_URL + "/verify-email#" + urlencode({"token": raw})
        context = {"verification_url": url}
        try:
            email = EmailMultiAlternatives(
                subject="[Diplomacie] Ověřte svůj e-mail",
                body=render_to_string("users/email/verify.txt", context),
                from_email=settings.DEFAULT_FROM_EMAIL, to=[user.email],
            )
            email.attach_alternative(render_to_string("users/email/verify.html", context), "text/html")
            if email.send(fail_silently=False) != 1:
                raise RuntimeError("Email backend did not accept delivery")
        except Exception as error:
            # Do not reveal recipients, links, tokens or SMTP exception messages.
            logger.error("Verification email failed (%s)", type(error).__name__)
            return False
        proof.email = user.email
        proof.token_digest = digest(raw)
        proof.expires_at = now + timedelta(hours=24)
        proof.consumed_at = None
        proof.save(update_fields=["email", "token_digest", "expires_at", "consumed_at"])
        return True


@sensitive_variables()
def confirm_verification(raw):
    if not isinstance(raw, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", raw):
        return False
    candidate = EmailVerification.objects.filter(token_digest=digest(raw)).first()
    if not candidate:
        return False
    with transaction.atomic():
        # Same lock order as resend, so confirmation and resend cannot race.
        user = User.objects.select_for_update().filter(pk=candidate.user_id).first()
        proof = EmailVerification.objects.select_for_update().filter(pk=candidate.pk).first()
        now = timezone.now()
        if (not user or not proof or not user.is_active or user.is_email_verified or proof.consumed_at or
                proof.token_digest != digest(raw) or not proof.expires_at or proof.expires_at <= now or
                proof.email.strip().lower() != user.email.strip().lower()):
            return False
        if not EmailVerification.objects.filter(pk=proof.pk, consumed_at=None, token_digest=digest(raw)).update(consumed_at=now):
            return False
        mark_verified(user)
        return True
