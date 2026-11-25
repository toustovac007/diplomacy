from django.core.cache import cache
from django.db import connection
from django.test import override_settings
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.games.models import Game, GamePlayer
from .models import User
from .email_verification import mark_verified


@override_settings(GAME_CREATE_COOLDOWN_SECONDS=0,EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class SQLInputTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.password="Bamboo!river83-moon"
        self.user=User.objects.create_user(username="owner",email="owner@example.test",password=self.password)
        mark_verified(self.user)
        self.client.credentials(HTTP_AUTHORIZATION="Bearer "+str(RefreshToken.for_user(self.user).access_token))

    def captured(self,payload,action):
        statements=[]
        def capture(execute,sql,params,many,context):
            statements.append((sql,params))
            return execute(sql,params,many,context)
        with connection.execute_wrapper(capture):
            result=action()
        self.assertTrue(any(payload in (params.values() if isinstance(params,dict) else params or ()) for _,params in statements))
        self.assertTrue(all(payload not in sql for sql,_ in statements))
        return result

    def test_game_names_with_quotes_and_sql_payloads_are_bound_as_data(self):
        payloads=["Robert's \"Aliance\"", "x' OR 1=1 --", "'; SELECT 1; --", "$$ UNION SELECT password FROM users_user --"]
        for payload in payloads:
            response=self.captured(payload,lambda:self.client.post('/api/games/',{'name':payload},format='json'))
            self.assertEqual(response.status_code,201)
            self.assertEqual(Game.objects.get(pk=response.data['id']).name,payload)
        self.assertEqual(User.objects.count(),1)
        self.assertEqual(GamePlayer.objects.count(),len(payloads))

    def test_login_payload_does_not_bypass_password_check(self):
        self.client.credentials()
        for payload in ("owner' OR '1'='1", "' UNION SELECT 1 --"):
            response=self.captured(payload,lambda:self.client.post('/api/token/',{'username':payload,'password':self.password}))
            self.assertEqual(response.status_code,401)
            self.assertNotIn('access',response.data)

    def test_malformed_ids_and_invitation_do_not_broaden_access(self):
        other=User.objects.create_user(username='other',email='other@example.test')
        private=Game.objects.create(name='Private',creator=other,is_public=False)
        response=self.client.post('/api/games/join-by-code/',{'invite_code':"' OR 1=1 --"})
        self.assertEqual(response.status_code,400)
        self.assertEqual(self.client.get('/api/games/1%20OR%201=1/').status_code,404)
        self.assertEqual(self.client.get(f'/api/games/{private.pk}/').status_code,404)
        self.assertFalse(private.players.exists())

    def test_new_username_limits_and_existing_long_username_login(self):
        for username in ('x'*33,"O'Brien",'a\nb','a\u202eb'):
            response=self.client.post('/api/users/register/',{'username':username,'email':'new@example.test','password':self.password})
            self.assertEqual(response.status_code,400)
            self.assertIn('username',response.data)
        cache.clear()
        response=self.client.post('/api/users/register/',{'username':'x'*32,'email':'new@example.test','password':self.password})
        self.assertEqual(response.status_code,201)
        legacy=User.objects.create_user(username='legacy_'+'x'*60,email='legacy@example.test',password=self.password)
        mark_verified(legacy)
        response=self.client.post('/api/token/',{'username':legacy.username,'password':self.password})
        self.assertEqual(response.status_code,200)
