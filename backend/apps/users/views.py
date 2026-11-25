from rest_framework import generics
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.settings import api_settings
from .throttles import LoginThrottle, RegisterThrottle, RefreshThrottle
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import RegisterSerializer
from .authentication import VerifiedTokenObtainPairSerializer, VerifiedTokenRefreshSerializer
from .throttles import VerificationRequestThrottle
from .email_verification import REQUEST_MESSAGE, request_verification


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [RegisterThrottle, VerificationRequestThrottle]

    def create(self, request, *args, **kwargs):
        data = self.get_serializer(data=request.data)
        data.is_valid(raise_exception=True)
        user = data.save()
        request_verification(user.pk)
        return Response({"detail": REQUEST_MESSAGE}, status=201,
                        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


class LoginView(TokenObtainPairView):
    throttle_classes = [LoginThrottle]
    serializer_class = VerifiedTokenObtainPairSerializer


class RefreshView(TokenRefreshView):
    throttle_classes = [RefreshThrottle]
    serializer_class = VerifiedTokenRefreshSerializer


class LogoutInput(serializers.Serializer):
    refresh = serializers.CharField(write_only=True)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        data = LogoutInput(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            token = RefreshToken(data.validated_data["refresh"])
        except TokenError:
            # Idempotent logout for expired/already-revoked tokens.
            return Response(status=204)
        if str(token[api_settings.USER_ID_CLAIM]) != str(request.user.pk):
            raise PermissionDenied("Cannot revoke another user's session.")
        token.blacklist()
        return Response(status=204)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({
            "username": request.user.username,
            "email": request.user.email,
        })


class TokensView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .tokens import wallet_snapshot
        return Response(wallet_snapshot(request.user.pk), headers={"Cache-Control": "no-store"})


class RankingView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.db.models import F
        from .tokens import account_balances
        leaders = account_balances().filter(is_active=True, email_verified_at__isnull=False,
                                             email__iexact=F("email_verified_for"))
        leaders = leaders.order_by("-tokens_total", "pk")[:10]
        return Response([{"rank": rank, "username": user.username,
                          "available": user.tokens_available, "frozen": user.tokens_frozen,
                          "total": user.tokens_total}
                         for rank, user in enumerate(leaders, 1)], headers={"Cache-Control": "no-store"})
