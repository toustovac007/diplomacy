from datetime import timedelta
import logging
import secrets
from urllib.parse import urlencode
from django.conf import settings
from django.http import HttpResponseRedirect
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from . import oauth, oauth_providers
from .models import OAuthFlow
from .throttles import OAuthStartThrottle, OAuthExchangeThrottle
from .email_verification import request_verification

logger = logging.getLogger(__name__)
COOKIE_PATH = "/api/users/oauth/"


class NoStoreView(APIView):
    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "no-store"
        response["Referrer-Policy"] = "no-referrer"
        return response


class PublicView(NoStoreView):
    permission_classes = [AllowAny]
    authentication_classes = []


class ProvidersView(PublicView):
    def get(self, request):
        return Response({p: oauth_providers.enabled(p) for p in oauth_providers.PROVIDERS})


class IdentitiesView(NoStoreView):
    def get(self, request):
        providers = set(request.user.social_identities.values_list("provider", flat=True))
        return Response({p: p in providers for p in oauth_providers.PROVIDERS})


class StartMixin:
    throttle_classes = [OAuthStartThrottle]
    intent = "login"

    @sensitive_variables()
    def post(self, request, provider):
        if not oauth_providers.enabled(provider):
            return Response({"detail": "provider_not_configured"}, status=400)
        state, verifier, binding = (secrets.token_urlsafe(32) for _ in range(3))
        nonce = secrets.token_urlsafe(32) if provider == "google" else ""
        try:
            url = oauth_providers.authorization_url(provider, state, verifier, nonce)
            oauth.cleanup()
            flow = OAuthFlow.objects.create(provider=provider, state_digest=oauth.digest(state),
                code_verifier=verifier, nonce=nonce, binding_digest=oauth.digest(binding), intent=self.intent,
                user=request.user if self.intent == "link" else None,
                expires_at=timezone.now() + timedelta(minutes=10))
        except Exception:
            logger.warning("OAuth start failed: category=oauth_failed")
            return Response({"detail": "oauth_failed"}, status=400)
        response = Response({"authorization_url": url})
        # Flow binding only, NOT an application session. Unique names preserve other tabs' flows.
        response.set_cookie(oauth.cookie_name(flow), binding, max_age=720,
                            httponly=True, secure=not settings.DEBUG, samesite="Lax", path=COOKIE_PATH)
        return response


class StartView(StartMixin, PublicView):
    pass


class LinkStartView(StartMixin, NoStoreView):
    intent = "link"


class CallbackView(PublicView):
    @sensitive_variables()
    def get(self, request, provider):
        flow = None
        try:
            if not oauth_providers.enabled(provider):
                raise oauth.OAuthFailure("provider_not_configured")
            flow = oauth.consume_flow(provider, request.query_params.get("state", ""), request.COOKIES)
            if request.query_params.get("error"):
                raise oauth.OAuthFailure("access_denied" if request.query_params["error"] == "access_denied" else "oauth_failed")
            code = request.query_params.get("code")
            if not code or len(code) > 4096:
                raise oauth.OAuthFailure()
            identity = oauth_providers.verified_identity(flow, code)
            user = oauth.resolve_user(flow, identity)
            if not user.is_email_verified:
                request_verification(user.pk)
                raise oauth.OAuthFailure("email_not_verified")
            result = {"linked": provider} if flow.intent == "link" else {"ticket": oauth.create_ticket(user, flow)}
        except Exception as error:
            category = error.code if isinstance(error, oauth.OAuthFailure) else "oauth_failed"
            logger.warning("OAuth callback failed: provider=%s category=%s", provider if provider in oauth_providers.PROVIDERS else "unknown", category)
            result = {"error": category}
        response = HttpResponseRedirect(settings.OAUTH_FRONTEND_URL + "/oauth/callback?" + urlencode(result))
        if flow and "ticket" not in result:
            response.delete_cookie(oauth.cookie_name(flow), path=COOKIE_PATH, samesite="Lax")
        return response


class ExchangeView(PublicView):
    throttle_classes = [OAuthExchangeThrottle]

    @sensitive_variables()
    def post(self, request):
        try:
            pair, cookie = oauth.exchange_ticket(request.data.get("ticket"), request.COOKIES)
        except Exception:
            return Response({"detail": "oauth_failed"}, status=400)
        response = Response(pair)
        response.delete_cookie(cookie, path=COOKIE_PATH, samesite="Lax")
        return response
