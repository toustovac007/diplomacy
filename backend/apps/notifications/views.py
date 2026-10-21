from rest_framework import generics, serializers
from rest_framework.permissions import IsAuthenticated
from .models import NotificationPreference


class PreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationPreference
        fields = ("email_phase_started", "email_deadline_reminder", "email_chat_message", "email_draw_events", "email_game_finished")

    def validate(self, data):
        if set(self.initial_data) - set(self.fields):
            raise serializers.ValidationError("Lze upravovat pouze vlastní nastavení upozornění.")
        return data


class PreferenceView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PreferenceSerializer

    def get_object(self):
        preference, _ = NotificationPreference.objects.get_or_create(user=self.request.user)
        return preference
