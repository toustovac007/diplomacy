from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from rest_framework import serializers
from django.db import IntegrityError, transaction


User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ("username", "email", "password")
        extra_kwargs = {"email": {"validators": []}}

    def validate_email(self, value):
        # Same case-insensitive policy already used by OAuth account lookup.
        return value.strip().lower()

    def validate(self, data):
        user = User(username=data.get("username", ""), email=data.get("email", ""))
        try:
            validate_password(data["password"], user=user)
        except ValidationError as error:
            raise serializers.ValidationError({"password": error.messages}) from error
        return data

    def create(self, validated_data):
        existing = User.objects.filter(email__iexact=validated_data["email"]).first()
        if existing:
            return existing  # Never replace an existing account's credentials.
        try:
            with transaction.atomic():
                return User.objects.create_user(**validated_data)
        except IntegrityError:
            existing = User.objects.filter(email__iexact=validated_data["email"]).first()
            if existing:
                return existing
            raise serializers.ValidationError({"username": "Toto uživatelské jméno už existuje."}) from None
