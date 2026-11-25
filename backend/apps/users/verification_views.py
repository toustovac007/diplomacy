from rest_framework import serializers
from collections.abc import Mapping
from rest_framework.response import Response

from .email_verification import REQUEST_MESSAGE, confirm_verification, request_verification
from .models import User
from .oauth_views import PublicView
from .throttles import VerificationRequestThrottle, VerificationConfirmThrottle


class ResendInput(serializers.Serializer):
    email = serializers.EmailField(max_length=254)


class ResendVerificationView(PublicView):
    throttle_classes = [VerificationRequestThrottle]

    def post(self, request):
        data = ResendInput(data=request.data)
        data.is_valid(raise_exception=True)
        user = User.objects.filter(email__iexact=data.validated_data["email"].strip()).first()
        if user:
            request_verification(user.pk)
        return Response({"detail": REQUEST_MESSAGE}, status=202)


class ConfirmVerificationView(PublicView):
    throttle_classes = [VerificationConfirmThrottle]

    def post(self, request):
        if not isinstance(request.data, Mapping) or not confirm_verification(request.data.get("token")):
            return Response({"detail": "verification_invalid"}, status=400)
        return Response({"detail": "email_verified"})
