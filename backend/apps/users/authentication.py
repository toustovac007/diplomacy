from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenObtainSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.settings import api_settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import update_last_login


def require_verified(user):
    if not user.is_email_verified:
        raise AuthenticationFailed("email_not_verified", code="email_not_verified")


class VerifiedJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        require_verified(user)
        return user


class VerifiedTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        TokenObtainSerializer.validate(self, attrs)
        require_verified(self.user)
        refresh = self.get_token(self.user)
        if api_settings.UPDATE_LAST_LOGIN:
            update_last_login(None, self.user)
        return {"access": str(refresh.access_token), "refresh": str(refresh)}


class VerifiedTokenRefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        token = RefreshToken(attrs["refresh"])
        user = get_user_model().objects.filter(pk=token.get(api_settings.USER_ID_CLAIM)).first()
        if not user or not user.is_active:
            raise AuthenticationFailed("no_active_account")
        require_verified(user)
        return super().validate(attrs)
