from django.urls import path

from .views import RegisterView, MeView, LogoutView
from .oauth_views import ProvidersView, IdentitiesView, StartView, LinkStartView, CallbackView, ExchangeView


urlpatterns = [
    path("oauth/providers/", ProvidersView.as_view()),
    path("oauth/identities/", IdentitiesView.as_view()),
    path("oauth/exchange/", ExchangeView.as_view()),
    path("oauth/<str:provider>/start/", StartView.as_view()),
    path("oauth/<str:provider>/link/start/", LinkStartView.as_view()),
    path("oauth/<str:provider>/callback/", CallbackView.as_view()),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("register/", RegisterView.as_view(), name="register"),
    path("me/", MeView.as_view(), name="me"),
]
