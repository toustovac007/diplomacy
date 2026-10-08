from django.urls import path

from .views import GameListCreateView,PublicGameListView,JoinGameView,StartGameView,GameDetailView


urlpatterns = [
    path("", GameListCreateView.as_view(), name="game-list-create"),

    path(
        "public/",
        PublicGameListView.as_view(),
        name="public-game-list"
    ),

    path(
        "<int:game_id>/join/",
        JoinGameView.as_view(),
        name="game-join"
    ),

    path(
        "<int:pk>/",
        GameDetailView.as_view(),
        name="game-detail",
    ),

    path(
        "<int:game_id>/start/",
        StartGameView.as_view(),
        name="game-start",
    ),
]