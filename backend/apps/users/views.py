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


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [RegisterThrottle]


class LoginView(TokenObtainPairView):
    throttle_classes = [LoginThrottle]


class RefreshView(TokenRefreshView):
    throttle_classes = [RefreshThrottle]


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
