from django.urls import path

from .views import GameListCreateView,PublicGameListView,JoinGameView,StartGameView,GameDetailView,JoinByCodeView
from .draw_views import CurrentDrawView, CreateDrawView, VoteDrawView, CancelDrawView
from .history_views import GameHistoryView


urlpatterns = [
    path("<int:game_id>/history/", GameHistoryView.as_view(), name="game-history"),
    path("<int:game_id>/history/<int:phase_id>/", GameHistoryView.as_view(), name="game-history-phase"),
    path("<int:game_id>/draw-proposals/", CreateDrawView.as_view()),
    path("<int:game_id>/draw-proposals/current/", CurrentDrawView.as_view()),
    path("<int:game_id>/draw-proposals/<int:proposal_id>/vote/", VoteDrawView.as_view()),
    path("<int:game_id>/draw-proposals/<int:proposal_id>/cancel/", CancelDrawView.as_view()),
    path("join-by-code/", JoinByCodeView.as_view(), name="game-join-by-code"),
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
