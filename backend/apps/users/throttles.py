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


class VerificationRequestThrottle(AuthIPThrottle):
    scope = "verification_request"

    def allow_request(self, request, view):
        from .email_verification import allow_request
        return allow_request(self.get_ident(request))

    def wait(self):
        return 3600


class VerificationConfirmThrottle(VerificationRequestThrottle):
    def allow_request(self, request, view):
        from .email_verification import allow_request
        return allow_request(self.get_ident(request), "confirm", 120)
