import api from "./api";

export async function getPreviousResolvedOrders(gameId) {
    return (await api.get(`orders/games/${gameId}/previous/`)).data;
}

export async function getAdjustmentStatus(gameId) {
    return (await api.get(`orders/games/${gameId}/adjustment-status/`)).data;
}

export async function getAdjustmentOrders(gameId) {
    return (await api.get(`orders/games/${gameId}/adjustments/`)).data;
}

export async function submitAdjustmentOrder(gameId, data) {
    return (await api.post(`orders/games/${gameId}/adjustments/`, data)).data;
}

export async function cancelAdjustmentOrder(gameId, orderId) {
    await api.delete(`orders/games/${gameId}/adjustments/${orderId}/`);
}

export async function getRetreatOrders(gameId) {
    const response = await api.get(`orders/games/${gameId}/retreats/`);
    return response.data;
}

export async function submitRetreatOrder(gameId, orderData) {
    const response = await api.post(`orders/games/${gameId}/retreats/`, orderData);
    return response.data;
}


export async function getOrders(gameId) {
    const response = await api.get(
        `orders/games/${gameId}/`
    );

    return response.data;
}


export async function submitOrder(gameId, orderData) {
    const response = await api.post(
        `orders/games/${gameId}/`,
        orderData
    );

    return response.data;
}
