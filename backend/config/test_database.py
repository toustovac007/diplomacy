import os
import runpy
from pathlib import Path
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase


class DatabaseSettingsTests(SimpleTestCase):
    def settings(self, **env):
        with patch.dict(os.environ, env, clear=True):
            return runpy.run_path(str(Path(__file__).with_name("settings.py")))

    def postgres(self, **overrides):
        return {"POSTGRES_DB": " diplomacy ", "POSTGRES_USER": " diplomacy ",
                "POSTGRES_PASSWORD": "test-only secret", "POSTGRES_HOST": " db.example ",
                "POSTGRES_PORT": "5433", **overrides}

    def production(self, **overrides):
        return {"DJANGO_DEBUG": "false", "DJANGO_SECRET_KEY": "test-only-config-key" * 5,
                "DJANGO_ALLOWED_HOSTS": "app.example", "FRONTEND_BASE_URL": "https://app.example", **overrides}

    def test_development_without_postgres_uses_existing_sqlite_path(self):
        data = self.settings(DJANGO_DEBUG="true")
        self.assertEqual(data["DATABASES"]["default"], {
            "ENGINE": "django.db.backends.sqlite3", "NAME": data["BASE_DIR"] / "db.sqlite3"})

    def test_postgres_selected_and_values_parsed_in_development_and_production(self):
        for env in (self.postgres(), self.production(**self.postgres())):
            with self.subTest(production="DJANGO_DEBUG" in env), self.assertNoLogs(level="DEBUG"):
                db = self.settings(**env)["DATABASES"]["default"]
            self.assertEqual(db["ENGINE"], "django.db.backends.postgresql")
            self.assertEqual((db["NAME"], db["USER"], db["HOST"], db["PORT"]),
                             ("diplomacy", "diplomacy", "db.example", 5433))
            self.assertIsInstance(db["PORT"], int)
            self.assertEqual(db["PASSWORD"], "test-only secret")
            self.assertEqual(db["CONN_MAX_AGE"], 0)

    def test_production_refuses_sqlite(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "PostgreSQL configuration is required"):
            self.settings(**self.production())

    def test_partial_configuration_never_silently_falls_back(self):
        for key in ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_CONN_MAX_AGE"):
            with self.subTest(key=key), self.assertRaises(ImproperlyConfigured) as raised:
                self.settings(**{key: "sensitive-test-value"})
            self.assertNotIn("sensitive-test-value", str(raised.exception))

    def test_invalid_numeric_settings_rejected_without_echoing_values(self):
        for key, values in {"POSTGRES_PORT": ("secret", "1.2", "", "0", "65536", "-1"),
                            "POSTGRES_CONN_MAX_AGE": ("secret", "-1", "1.2")}.items():
            for value in values:
                with self.subTest(key=key, value=value), self.assertRaises(ImproperlyConfigured) as raised:
                    self.settings(**self.postgres(**{key: value}))
                self.assertNotIn("test-only secret", str(raised.exception))
                self.assertNotIn("secret", str(raised.exception))

    def test_defaults_and_optional_connection_age(self):
        env = self.postgres(POSTGRES_CONN_MAX_AGE="60")
        del env["POSTGRES_HOST"], env["POSTGRES_PORT"]
        db = self.settings(**env)["DATABASES"]["default"]
        self.assertEqual((db["HOST"], db["PORT"], db["CONN_MAX_AGE"]), ("127.0.0.1", 5432, 60))
