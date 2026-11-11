from django.urls import path
from .views import ConversationList, ConversationDetail, Messages, ReadConversation

urlpatterns = [
    path("", ConversationList.as_view(), name="chat-list"),
    path("<int:conversation_id>/", ConversationDetail.as_view(), name="chat-detail"),
    path("<int:conversation_id>/messages/", Messages.as_view(), name="chat-messages"),
    path("<int:conversation_id>/read/", ReadConversation.as_view(), name="chat-read"),
]
