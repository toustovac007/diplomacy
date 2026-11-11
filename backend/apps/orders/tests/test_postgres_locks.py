"""Compile queries issued by real resolvers using PostgreSQL's SQL compiler.

This can detect lock scope regressions without a server. It does not substitute
for running the complete adjudication suite on a live PostgreSQL test database.
"""
from unittest.mock import patch
from django.db.backends.postgresql.base import DatabaseWrapper
from django.db.models.sql.compiler import SQLCompiler
from django.test import TestCase
from apps.games.readiness_tests import fixture
from apps.games.models import Unit
from apps.maps.models import Province
from apps.orders.models import Order, AdjustmentOrder
from apps.orders.services.adjudication import resolve_movement_phase
from apps.orders.services.retreat import resolve_retreat_phase
from apps.orders.services.adjustments import resolve_adjustment_phase


class ResolverLockScopeTests(TestCase):
    def test_real_resolvers_lock_only_base_rows_with_nullable_related_fields(self):
        game, players, phase = fixture()
        pg = DatabaseWrapper({"ENGINE": "django.db.backends.postgresql", "NAME": "compile_only"}, alias="compile_only")
        original = SQLCompiler.as_sql
        queries = []

        def compile_sql(compiler, *args, **kwargs):
            result = original(compiler, *args, **kwargs)
            if (compiler.connection.alias != "compile_only" and compiler.query.select_for_update
                    and compiler.query.model in (Unit, Order, AdjustmentOrder)):
                sql, _ = compiler.query.clone().get_compiler(connection=pg).as_sql()
                queries.append((compiler.query.model, sql))
            return result

        with patch.object(pg, "get_autocommit", return_value=False), patch.object(SQLCompiler, "as_sql", compile_sql):
            unit = Unit.objects.create(game=game, owner=players[0], province=Province.objects.get(code="PAR"), unit_type="army")
            resolve_movement_phase(phase)
            phase = game.phases.get(status="open")
            phase.phase_type = "retreat"
            phase.save()
            unit.is_dislodged = True
            unit.save()
            resolve_retreat_phase(phase)
            phase = game.phases.get(status="open")
            phase.phase_type, phase.season = "adjustment", "winter"
            phase.save()
            resolve_adjustment_phase(phase, allow_automatic_disbands=True)
        self.assertEqual([model for model, _ in queries], [Unit, Order, Unit, AdjustmentOrder])
        for model, sql in queries:
            self.assertIn("LEFT OUTER JOIN", sql)
            self.assertTrue(sql.endswith(f'FOR UPDATE OF "{model._meta.db_table}"'), sql)
