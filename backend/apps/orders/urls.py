from django.urls import path

from .views import (
    OrderListCreateView,
    ResolvePhaseView,
    RetreatOrderListCreateView,
    ResolveRetreatPhaseView,
    AdjustmentOrderListCreateView,
    ResolveAdjustmentPhaseView,
)


urlpatterns = [
    path(
        "games/<int:game_id>/",
        OrderListCreateView.as_view(),
        name="order-list-create",
    ),

    path(
        "games/<int:game_id>/resolve/",
        ResolvePhaseView.as_view(),
        name="resolve-phase",
    ),

    path(
        "games/<int:game_id>/retreats/",
        RetreatOrderListCreateView.as_view(),
        name="retreat-order-list-create",
    ),

    path(
        "games/<int:game_id>/resolve-retreat/",
        ResolveRetreatPhaseView.as_view(),
        name="resolve-retreat-phase",
    ),
    path(
        "games/<int:game_id>/adjustments/",
        AdjustmentOrderListCreateView.as_view(),
        name="adjustment-order-list-create",
    ),

    path(
        "games/<int:game_id>/resolve-adjustment/",
        ResolveAdjustmentPhaseView.as_view(),
        name="resolve-adjustment-phase",
    ),
]