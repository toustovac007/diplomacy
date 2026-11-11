import importlib.util
import os
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken
from config.environment import env_bool


class EnvironmentTests(SimpleTestCase):
    def settings(self, **env):
        with patch.dict(os.environ, env, clear=True):
            spec = importlib.util.spec_from_file_location("config.security_settings_test", Path(__file__).parents[2] / "config" / "settings.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module

    def test_boolean_parser(self):
        for value in ("1", "TRUE", "yes", "on"):
            with patch.dict(os.environ, {"BOOL_TEST": value}):
                self.assertTrue(env_bool("BOOL_TEST"))
        for value in ("0", "false", "NO", "off"):
            with patch.dict(os.environ, {"BOOL_TEST": value}):
                self.assertFalse(env_bool("BOOL_TEST"))
        with patch.dict(os.environ, {"BOOL_TEST": "typo"}), self.assertRaises(ImproperlyConfigured):
            env_bool("BOOL_TEST")

    def test_environment_policy(self):
        dev = self.settings()
        self.assertTrue(dev.DEBUG)
        self.assertTrue(dev.SECRET_KEY.startswith("development-only"))
        self.assertTrue(dev.ALLOW_MANUAL_PHASE_RESOLVE)
        self.assertFalse(dev.SECURE_SSL_REDIRECT)
        self.assertEqual(dev.SECURE_HSTS_SECONDS, 0)
        with self.assertRaises(ImproperlyConfigured):
            self.settings(DJANGO_DEBUG="false")
        env = dict(DJANGO_DEBUG="false", DJANGO_SECRET_KEY="test-only-production-policy-key" * 3,
                   POSTGRES_DB="settings_test", POSTGRES_USER="settings_test", POSTGRES_PASSWORD="test-only",
                   DJANGO_ALLOWED_HOSTS=" game.example, api.example ", FRONTEND_BASE_URL="https://game.example",
                   DJANGO_CORS_ALLOWED_ORIGINS="https://game.example, https://other.example")
        prod = self.settings(**env)
        self.assertEqual(prod.ALLOWED_HOSTS, ["game.example", "api.example"])
        self.assertEqual(prod.CORS_ALLOWED_ORIGINS, ["https://game.example", "https://other.example"])
        self.assertTrue(prod.SECURE_SSL_REDIRECT and prod.CSRF_COOKIE_SECURE and prod.SESSION_COOKIE_SECURE)
        self.assertGreater(prod.SECURE_HSTS_SECONDS, 0)
        self.assertFalse(prod.ALLOW_MANUAL_PHASE_RESOLVE)
        self.assertFalse(hasattr(prod, "SECURE_PROXY_SSL_HEADER"))
        self.assertEqual(self.settings(**env, DJANGO_TRUST_X_FORWARDED_PROTO="true").SECURE_PROXY_SSL_HEADER,
                         ("HTTP_X_FORWARDED_PROTO", "https"))
        for key, value in (("DJANGO_ALLOWED_HOSTS", "*"), ("DJANGO_CORS_ALLOWED_ORIGINS", "https://*.example"),
                           ("DJANGO_DEBUG", "typo"), ("FRONTEND_BASE_URL", "http://localhost:5173")):
            with self.subTest(key=key), self.assertRaises(ImproperlyConfigured):
                self.settings(**{**env, key: value})


class AuthenticationSecurityTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.password = "Bamboo!river83-moon"
        self.user = get_user_model().objects.create_user(username="alice", email="alice@example.test", password=self.password)

    def test_registration_validates_password_and_never_exposes_it(self):
        data = {"username": "bravo", "email": "bravo@example.test", "password": "12345678"}
        self.assertEqual(self.client.post('/api/users/register/', data).status_code, 400)
        data["password"] = self.password
        response = self.client.post('/api/users/register/', {**data, "is_staff": True})
        self.assertEqual(response.status_code, 201)
        self.assertNotIn("password", response.data)
        user = get_user_model().objects.get(username="bravo")
        self.assertTrue(user.check_password(self.password))
        self.assertNotEqual(user.password, self.password)
        self.assertFalse(user.is_staff)

    def test_login_rotation_logout_and_foreign_revoke(self):
        response = self.client.post('/api/token/', {"username": "alice", "password": self.password})
        self.assertEqual(response.status_code, 200)
        first = response.data["refresh"]
        rotated = self.client.post('/api/token/refresh/', {"refresh": first})
        self.assertEqual(rotated.status_code, 200)
        self.assertNotEqual(rotated.data["refresh"], first)
        self.assertEqual(self.client.post('/api/token/refresh/', {"refresh": first}).status_code, 401)
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + rotated.data["access"])
        other = get_user_model().objects.create_user(username="other", email="other@example.test")
        foreign = str(RefreshToken.for_user(other))
        self.assertEqual(self.client.post('/api/users/logout/', {"refresh": foreign}).status_code, 403)
        self.assertEqual(self.client.post('/api/users/logout/', {"refresh": rotated.data["refresh"]}).status_code, 204)
        self.assertEqual(self.client.post('/api/token/refresh/', {"refresh": rotated.data["refresh"]}).status_code, 401)
        self.assertEqual(self.client.post('/api/users/logout/', {"refresh": "invalid"}).status_code, 204)

    def test_generic_bad_credentials(self):
        known = self.client.post('/api/token/', {"username": "alice", "password": "wrong"})
        unknown = self.client.post('/api/token/', {"username": "unknown", "password": "wrong"})
        self.assertEqual(known.status_code, 401)
        self.assertEqual(known.data, unknown.data)

    def test_targeted_ip_throttles(self):
        for path, limit in (("token/", 10), ("users/register/", 5), ("token/refresh/", 30)):
            cache.clear()
            for _ in range(limit):
                self.assertNotEqual(self.client.post('/api/' + path, {}).status_code, 429)
            self.assertEqual(self.client.post('/api/' + path, {}).status_code, 429)
            # Polling endpoints are not subject to the auth throttle.
            self.client.force_authenticate(self.user)
            self.assertEqual(self.client.get('/api/users/me/').status_code, 200)
            self.client.force_authenticate(None)
