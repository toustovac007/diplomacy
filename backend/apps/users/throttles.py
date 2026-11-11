from rest_framework.throttling import SimpleRateThrottle


class AuthIPThrottle(SimpleRateThrottle):
    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class LoginThrottle(AuthIPThrottle):
    scope = "login"


class RegisterThrottle(AuthIPThrottle):
    scope = "register"


class RefreshThrottle(AuthIPThrottle):
    scope = "refresh"


class OAuthStartThrottle(AuthIPThrottle):
    scope = "oauth_start"


class OAuthExchangeThrottle(AuthIPThrottle):
    scope = "oauth_exchange"
