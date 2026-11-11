import base64
import hashlib
import json
import time
from datetime import timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import jwt
import requests
from cryptography.hazmat.primitives.asymmetric import rsa
from django.core.cache import cache
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from .models import User, SocialIdentity, OAuthFlow, OAuthLoginTicket
from . import oauth

CONFIG = {p: {"client_id": p + "-client", "client_secret": "test-secret",
              "redirect_uri": f"http://127.0.0.1:8000/api/users/oauth/{p}/callback/"}
          for p in ("google", "github")}


@override_settings(OAUTH_PROVIDERS=CONFIG, OAUTH_FRONTEND_URL="http://127.0.0.1:5173")
class OAuthTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(cls.key.public_key()))
        cls.jwk.update(kid="test", use="sig", alg="RS256")

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.claim_changes = {}
        self.profile = {"id": 42, "login": "player"}
        self.emails = [{"email": "player@example.com", "verified": True, "primary": True}]
        self.http_calls = []
        self.http = patch("requests.sessions.Session.send", side_effect=self.send)
        self.http.start()
        self.addCleanup(self.http.stop)

    def send(self, request, **kwargs):
        self.http_calls.append(request)
        url = request.url
        if url.endswith(".well-known/openid-configuration"):
            data = {"issuer": "https://accounts.google.com", "authorization_endpoint": "https://accounts.google.com/auth",
                    "token_endpoint": "https://accounts.google.com/token", "jwks_uri": "https://accounts.google.com/keys",
                    "id_token_signing_alg_values_supported": ["RS256"]}
        elif url.endswith("/keys"):
            data = {"keys": [self.jwk]}
        elif url.endswith("/token"):
            claims = {"iss": "https://accounts.google.com", "aud": "google-client", "sub": "google-sub",
                      "iat": int(time.time()), "exp": int(time.time()) + 300, "nonce": self.nonce,
                      "email": "player@example.com", "email_verified": True}
            claims.update(self.claim_changes)
            data = {"access_token": "provider-secret", "token_type": "Bearer",
                    "id_token": jwt.encode(claims, self.key, algorithm="RS256", headers={"kid": "test"})}
        elif url.endswith("/access_token"):
            data = {"access_token": "provider-secret", "token_type": "bearer"}
        elif url.endswith("/user/emails"):
            data = self.emails
        elif url.endswith("/user"):
            data = self.profile
        else:
            raise AssertionError("Unexpected provider request")
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps(data).encode()
        response.headers["Content-Type"] = "application/json"
        response.request = request
        return response

    def start(self, provider="google", link=False):
        response = self.client.post(f"/api/users/oauth/{provider}/{'link/' if link else ''}start/", {}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        params = parse_qs(urlsplit(response.data["authorization_url"]).query)
        self.state = params["state"][0]
        self.nonce = params.get("nonce", [""])[0]
        return params

    def callback(self, provider="google", **params):
        response = self.client.get(f"/api/users/oauth/{provider}/callback/", {"state": self.state, "code": "test-code", **params})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("http://127.0.0.1:5173/oauth/callback?"))
        self.assertNotIn("access=", response.url)
        self.assertNotIn("refresh=", response.url)
        self.assertEqual(response["Cache-Control"], "no-store")
        return {k: v[0] for k, v in parse_qs(urlsplit(response.url).query).items()}

    def exchange(self, ticket):
        return self.client.post("/api/users/oauth/exchange/", {"ticket": ticket}, format="json")

    def test_start_scopes_state_pkce_and_nonce(self):
        for provider in CONFIG:
            params = self.start(provider)
            flow = OAuthFlow.objects.get(state_digest=oauth.digest(self.state))
            self.assertEqual(params["code_challenge_method"], ["S256"])
            challenge = base64.urlsafe_b64encode(hashlib.sha256(flow.code_verifier.encode()).digest()).rstrip(b"=").decode()
            self.assertEqual(params["code_challenge"], [challenge])
            self.assertEqual(params["scope"], ["openid email profile" if provider == "google" else "read:user user:email"])
            self.assertEqual(bool(flow.nonce), provider == "google")
            old_state = self.state
            self.start(provider)
            self.assertNotEqual(old_state, self.state)
            self.assertNotIn("client_secret", params)

    def test_google_signup_ticket_and_standard_jwt_lifecycle(self):
        self.start()
        ticket = self.callback()["ticket"]
        user = User.objects.get()
        self.assertFalse(user.has_usable_password())
        self.assertEqual(user.email, "player@example.com")
        self.assertEqual(SocialIdentity.objects.get().subject, "google-sub")
        self.assertNotEqual(OAuthLoginTicket.objects.get().token_digest, ticket)
        self.assertEqual(OAuthFlow.objects.get().code_verifier, "")
        response = self.exchange(ticket)
        self.assertEqual(response.status_code, 200)
        pair = response.data
        self.assertEqual(AccessToken(pair["access"])["user_id"], str(user.pk))
        self.assertEqual(self.exchange(ticket).status_code, 400)
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + pair["access"])
        self.assertEqual(self.client.get("/api/users/me/").data["username"], user.username)
        rotated = self.client.post("/api/token/refresh/", {"refresh": pair["refresh"]}).data
        self.assertNotEqual(rotated["refresh"], pair["refresh"])
        self.assertEqual(self.client.post("/api/token/refresh/", {"refresh": pair["refresh"]}).status_code, 401)
        self.assertEqual(self.client.post("/api/users/logout/", {"refresh": rotated["refresh"]}).status_code, 204)
        self.assertEqual(self.client.post("/api/token/refresh/", {"refresh": rotated["refresh"]}).status_code, 401)

    def test_github_verified_numeric_subject_collision_and_no_persisted_token(self):
        User.objects.create_user(username="player", email="other@example.com")
        self.start("github")
        self.assertIn("ticket", self.callback("github"))
        identity = SocialIdentity.objects.get()
        self.assertEqual(identity.subject, "42")
        self.assertTrue(identity.user.username.startswith("player_"))
        self.assertFalse(identity.user.has_usable_password())
        for model in (User, SocialIdentity, OAuthFlow, OAuthLoginTicket):
            self.assertNotIn("provider-secret", str(list(model.objects.values())))
        token_request = next(r for r in self.http_calls if r.url.endswith("/access_token"))
        self.assertIn("code_verifier=", token_request.body)

    def test_github_email_verification_and_deterministic_preference(self):
        self.emails[0]["verified"] = False
        self.start("github")
        self.assertEqual(self.callback("github"), {"error": "verified_email_required"})
        self.assertFalse(User.objects.exists())
        self.emails += [{"email": "z@example.com", "verified": True}, {"email": "a@example.com", "verified": True}]
        self.start("github")
        self.assertIn("ticket", self.callback("github"))
        self.assertEqual(User.objects.get().email, "a@example.com")

    def test_state_expiry_replay_provider_mismatch_and_browser_binding(self):
        for provider in CONFIG:
            self.start(provider)
            self.assertEqual(self.callback(provider, state="wrong"), {"error": "oauth_state_invalid"})
            cookies = self.client.cookies.copy()
            self.client.cookies.clear()
            self.assertEqual(self.callback(provider), {"error": "oauth_state_invalid"})
            self.client.cookies = cookies
            OAuthFlow.objects.filter(state_digest=oauth.digest(self.state)).update(expires_at=timezone.now() - timedelta(seconds=1))
            self.assertEqual(self.callback(provider), {"error": "oauth_expired"})
            self.start(provider)
            self.assertEqual(self.callback(provider, error="access_denied"), {"error": "access_denied"})
            self.assertEqual(self.callback(provider), {"error": "oauth_state_invalid"})
        self.start("google")
        self.assertEqual(self.callback("github"), {"error": "oauth_state_invalid"})

    def test_google_invalid_claims_and_signature_fail_closed(self):
        for changes in ({"iss": "https://evil.test"}, {"aud": "other"}, {"nonce": "wrong"},
                        {"nonce": None}, {"exp": int(time.time()) - 300}, {"sub": ""}):
            with self.subTest(changes=changes):
                self.claim_changes = changes
                self.start()
                self.assertEqual(self.callback(), {"error": "oauth_failed"})
        self.claim_changes = {}
        self.start()
        with patch.object(self, "key", rsa.generate_private_key(public_exponent=65537, key_size=2048)):
            self.assertEqual(self.callback(), {"error": "oauth_failed"})
        self.assertFalse(User.objects.exists())
        self.claim_changes = {"email_verified": False}
        self.start()
        self.assertEqual(self.callback(), {"error": "verified_email_required"})

    def test_existing_email_never_auto_links_and_existing_subject_ignores_email(self):
        local = User.objects.create_user(username="local", email="PLAYER@example.com", password="test-password")
        self.start()
        self.assertEqual(self.callback(), {"error": "account_link_required"})
        self.assertFalse(SocialIdentity.objects.exists())
        SocialIdentity.objects.create(user=local, provider="google", subject="google-sub")
        self.claim_changes = {"email": "changed@example.com", "email_verified": False}
        self.start()
        ticket = self.callback()["ticket"]
        self.assertEqual(OAuthLoginTicket.objects.get(token_digest=oauth.digest(ticket)).user, local)
        self.assertEqual(User.objects.count(), 1)

    def test_explicit_link_different_email_idempotence_ownership_and_status(self):
        self.assertEqual(self.client.post("/api/users/oauth/github/link/start/").status_code, 401)
        local = User.objects.create_user(username="local", email="local@example.com")
        self.client.force_authenticate(local)
        for _ in range(2):
            self.start("github", link=True)
            self.assertEqual(self.callback("github"), {"linked": "github"})
        self.assertEqual(SocialIdentity.objects.get().user, local)
        self.assertFalse(OAuthLoginTicket.objects.exists())
        self.assertEqual(self.client.get("/api/users/oauth/identities/").data, {"google": False, "github": True})
        self.profile["id"] = 43
        self.start("github", link=True)
        self.assertEqual(self.callback("github"), {"error": "identity_in_use"})
        self.profile["id"] = 42
        other = User.objects.create_superuser(username="admin", email="admin@example.com", password="test-password")
        self.client.force_authenticate(other)
        self.start("github", link=True)
        self.assertEqual(self.callback("github"), {"error": "identity_in_use"})
        self.assertEqual(self.client.get("/api/users/oauth/identities/").data, {"google": False, "github": False})
        self.client.force_authenticate(None)
        self.start("github")
        ticket = self.callback("github")["ticket"]
        self.assertEqual(OAuthLoginTicket.objects.get(token_digest=oauth.digest(ticket)).user, local)

    def test_ticket_expired_invalid_and_wrong_browser(self):
        self.start()
        ticket = self.callback()["ticket"]
        cookies = self.client.cookies.copy()
        self.client.cookies.clear()
        self.assertEqual(self.exchange(ticket).status_code, 400)
        self.client.cookies = cookies
        OAuthLoginTicket.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.exchange(ticket).status_code, 400)
        self.assertEqual(self.exchange("invalid").status_code, 400)

    def test_disabled_providers_and_inactive_user(self):
        with override_settings(OAUTH_PROVIDERS={p: dict.fromkeys(CONFIG[p], "") for p in CONFIG}):
            self.assertEqual(self.client.get("/api/users/oauth/providers/").data, {"google": False, "github": False})
            self.assertEqual(self.client.post("/api/users/oauth/google/start/").status_code, 400)
        local = User.objects.create_user(username="inactive", email="inactive@example.com", is_active=False)
        SocialIdentity.objects.create(user=local, provider="google", subject="google-sub")
        self.start()
        self.assertEqual(self.callback(), {"error": "oauth_failed"})

    def test_safe_provider_failure_and_cleanup(self):
        self.start()
        with patch("apps.users.oauth_providers.verified_identity", side_effect=RuntimeError("SECRET")):
            self.assertEqual(self.callback(), {"error": "oauth_failed"})
        OAuthFlow.objects.update(expires_at=timezone.now() - timedelta(hours=2))
        self.start()
        self.assertEqual(OAuthFlow.objects.count(), 1)

    def test_protocol_logs_are_suppressed_and_callback_urls_redacted(self):
        import logging
        from .oauth_logging import OAuthPrivacyFilter
        record = logging.LogRecord("django.server", logging.INFO, "", 0,
            'GET /api/users/oauth/google/callback/?code=SECRET&state=SECRET', (), None)
        self.assertTrue(OAuthPrivacyFilter().filter(record))
        self.assertNotIn("SECRET", record.getMessage())
        for name in ("authlib", "urllib3"):
            logger = logging.getLogger(name)
            self.assertFalse(logger.propagate)
            self.assertTrue(any(isinstance(handler, logging.NullHandler) for handler in logger.handlers))

    def test_throttles(self):
        for _ in range(20):
            self.client.post("/api/users/oauth/unknown/start/")
        self.assertEqual(self.client.post("/api/users/oauth/unknown/start/").status_code, 429)
        for _ in range(30):
            self.exchange("invalid")
        self.assertEqual(self.exchange("invalid").status_code, 429)


class TicketConcurrencyTests(TransactionTestCase):
    def test_two_simultaneous_exchanges_issue_exactly_one_pair(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from django.db import connections, OperationalError
        user = User.objects.create_user(username="concurrent", email="concurrent@example.com")
        OAuthLoginTicket.objects.create(user=user, token_digest=oauth.digest("ticket"),
            binding_digest=oauth.digest("browser"), cookie_name="oauth_test",
            expires_at=timezone.now() + timedelta(seconds=90))
        barrier = Barrier(2)

        def exchange():
            barrier.wait(timeout=5)
            try:
                return bool(oauth.exchange_ticket("ticket", {"oauth_test": "browser"})[0]["access"])
            except (oauth.OAuthFailure, OperationalError):
                return False
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: exchange(), range(2)))
        self.assertEqual(sorted(results), [False, True])
        self.assertIsNotNone(OAuthLoginTicket.objects.get().used_at)
