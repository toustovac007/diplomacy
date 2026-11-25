"""Short-lived OAuth proofs followed by the ordinary application JWT session."""
from datetime import timedelta
import hashlib
import re
import secrets
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken
from .models import OAuthFlow, OAuthLoginTicket, SocialIdentity, User
from .email_verification import mark_verified


class OAuthFailure(Exception):
    def __init__(self, code="oauth_failed"):
        self.code = code


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def cookie_name(flow):
    return "oauth_" + flow.state_digest


def consume_flow(provider, state, cookies):
    if not isinstance(state, str) or len(state) > 256:
        raise OAuthFailure("oauth_state_invalid")
    with transaction.atomic():
        flow = OAuthFlow.objects.select_for_update().filter(provider=provider, state_digest=digest(state)).first()
        if not flow or flow.consumed_at or not secrets.compare_digest(
                flow.binding_digest, digest(cookies.get(cookie_name(flow), ""))):
            raise OAuthFailure("oauth_state_invalid")
        now = timezone.now()
        if flow.expires_at <= now:
            raise OAuthFailure("oauth_expired")
        # CAS also protects SQLite, where select_for_update is a no-op.
        if not OAuthFlow.objects.filter(pk=flow.pk, consumed_at=None, expires_at__gt=now).update(
                consumed_at=now, code_verifier="", nonce=""):
            raise OAuthFailure("oauth_state_invalid")
        return flow  # Only this callback retains the original verifier/nonce.


def resolve_user(flow, identity):
    subject = identity["subject"]
    for attempt in range(5):
        try:
            with transaction.atomic():
                linked = SocialIdentity.objects.select_for_update().select_related("user").filter(
                    provider=flow.provider, subject=subject).first()
                if linked:
                    if flow.intent == "link" and linked.user_id != flow.user_id:
                        raise OAuthFailure("identity_in_use")
                    user = linked.user
                elif flow.intent == "link":
                    user = User.objects.select_for_update().get(pk=flow.user_id)
                    if SocialIdentity.objects.filter(user=user, provider=flow.provider).exists():
                        raise OAuthFailure("identity_in_use")
                    linked = SocialIdentity.objects.create(user=user, provider=flow.provider, subject=subject)
                else:
                    email = identity.get("email")
                    if not email:
                        raise OAuthFailure("verified_email_required")
                    if User.objects.filter(email__iexact=email).exists():
                        raise OAuthFailure("account_link_required")
                    # Leave room for the collision suffix within the new-name limit.
                    base = re.sub(r"[^\w.@+-]", "", str(identity.get("username", "")))[:User.NEW_USERNAME_MAX_LENGTH - 9] or "player"
                    username = base
                    if attempt or User.objects.filter(username=username).exists():
                        username = base + "_" + secrets.token_hex(4)
                    user = User(username=username, email=email)
                    user.set_unusable_password()
                    user.save()
                    linked = SocialIdentity.objects.create(user=user, provider=flow.provider, subject=subject)
                if not user.is_active:
                    raise OAuthFailure()
                if (not user.is_email_verified and identity.get("email") and
                        identity.get("email_is_authoritative", False) and
                        identity["email"].strip().lower() == user.email.strip().lower()):
                    mark_verified(user)
                linked.last_login_at = timezone.now()
                linked.save(update_fields=["last_login_at"])
                return user
        except IntegrityError:
            # Roll back the entire creation, including the user, then read the winner.
            continue
    raise OAuthFailure()


def create_ticket(user, flow):
    if not user.is_active or not user.is_email_verified:
        raise OAuthFailure("email_not_verified")
    ticket = secrets.token_urlsafe(32)
    OAuthLoginTicket.objects.create(user=user, token_digest=digest(ticket),
        binding_digest=flow.binding_digest, cookie_name=cookie_name(flow),
        expires_at=timezone.now() + timedelta(seconds=90))
    return ticket


def exchange_ticket(raw, cookies):
    if not isinstance(raw, str) or not raw or len(raw) > 256:
        raise OAuthFailure()
    # Read binding before opening the write transaction: avoid a SQLite
    # read-to-write lock upgrade deadlock between two simultaneous exchanges.
    candidate = OAuthLoginTicket.objects.filter(token_digest=digest(raw)).first()
    if not candidate or not secrets.compare_digest(candidate.binding_digest, digest(cookies.get(candidate.cookie_name, ""))):
        raise OAuthFailure()
    with transaction.atomic():
        now = timezone.now()
        if not OAuthLoginTicket.objects.filter(pk=candidate.pk, used_at=None, expires_at__gt=now).update(used_at=now):
            raise OAuthFailure()
        ticket = OAuthLoginTicket.objects.select_for_update().select_related("user").filter(token_digest=digest(raw)).first()
        if not ticket or not ticket.user.is_active or not ticket.user.is_email_verified:
            raise OAuthFailure()
        refresh = RefreshToken.for_user(ticket.user)
        return {"access": str(refresh.access_token), "refresh": str(refresh)}, ticket.cookie_name


def cleanup():
    cutoff = timezone.now() - timedelta(hours=1)
    OAuthFlow.objects.filter(expires_at__lt=cutoff).delete()
    OAuthLoginTicket.objects.filter(expires_at__lt=cutoff).delete()
