# Create your models here.

from django.contrib.auth.models import AbstractUser
from django.db import models, transaction
from django.utils import timezone


class User(AbstractUser):
    NEW_USERNAME_MAX_LENGTH = 32
    email = models.EmailField(unique=True)
    last_game_created_at = models.DateTimeField(null=True, blank=True, editable=False)
    tokens_available = models.PositiveBigIntegerField(default=1000, editable=False)
    last_token_refill_at = models.DateTimeField(null=True, blank=True, editable=False)
    token_refill_due_at = models.DateTimeField(null=True, blank=True, db_index=True, editable=False)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    email_verified_for = models.EmailField(blank=True, default="")

    @property
    def is_email_verified(self):
        # Changing the address (including through admin) invalidates its proof.
        return bool(self.email and self.email_verified_at and
                    self.email.strip().lower() == self.email_verified_for.strip().lower())

    def save(self, *args, **kwargs):
        fields = kwargs.get("update_fields")
        if self.pk and (fields is None or "email" in fields):
            with transaction.atomic():
                previous = type(self).objects.select_for_update().filter(pk=self.pk).first()
                if previous and previous.email.strip().lower() != self.email.strip().lower():
                    self.email_verified_at, self.email_verified_for = None, ""
                    if fields is not None:
                        kwargs["update_fields"] = set(fields) | {"email_verified_at", "email_verified_for"}
                    EmailVerification.objects.filter(user_id=self.pk).update(token_digest=None, consumed_at=timezone.now())
                return super().save(*args, **kwargs)
        return super().save(*args, **kwargs)


class EmailVerification(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    email = models.EmailField(blank=True)
    token_digest = models.CharField(max_length=64, null=True, unique=True)
    expires_at = models.DateTimeField(null=True)
    consumed_at = models.DateTimeField(null=True)
    last_sent_at = models.DateTimeField(null=True)
    window_start = models.DateTimeField(null=True)
    send_count = models.PositiveIntegerField(default=0)


class TokenEntry(models.Model):
    """Movements relative to the account's one-time initial balance of 1000."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="token_entries")
    game = models.ForeignKey("games.Game", null=True, on_delete=models.SET_NULL, related_name="token_entries")
    kind = models.CharField(max_length=16, choices=[
        ("stake", "Stake"), ("forfeit", "Elimination"),
        ("settlement", "Settlement"), ("refill", "Minimum refill"),
        ("refund", "Returned stake"),
    ])
    available_delta = models.BigIntegerField(default=0)
    frozen_delta = models.BigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["pk"]


class VerificationRequestLimit(models.Model):
    key = models.CharField(max_length=64, primary_key=True)
    window_start = models.DateTimeField()
    count = models.PositiveIntegerField(default=0)


PROVIDERS = [("google", "Google"), ("github", "GitHub")]


class SocialIdentity(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="social_identities")
    provider = models.CharField(max_length=10, choices=PROVIDERS)
    subject = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    last_login_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["provider", "subject"], name="unique_provider_subject"),
            models.UniqueConstraint(fields=["user", "provider"], name="unique_user_provider"),
        ]


class OAuthFlow(models.Model):
    provider = models.CharField(max_length=10, choices=PROVIDERS)
    state_digest = models.CharField(max_length=64, unique=True)
    code_verifier = models.CharField(max_length=128)
    nonce = models.CharField(max_length=128, blank=True)
    intent = models.CharField(max_length=5, choices=[("login", "Login"), ("link", "Link")])
    user = models.ForeignKey(User, null=True, on_delete=models.CASCADE)
    binding_digest = models.CharField(max_length=64)
    expires_at = models.DateTimeField(db_index=True)
    consumed_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)


class OAuthLoginTicket(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    token_digest = models.CharField(max_length=64, unique=True)
    binding_digest = models.CharField(max_length=64)
    cookie_name = models.CharField(max_length=80)
    expires_at = models.DateTimeField(db_index=True)
    used_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
