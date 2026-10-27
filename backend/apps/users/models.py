# Create your models here.

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    email = models.EmailField(unique=True)


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
