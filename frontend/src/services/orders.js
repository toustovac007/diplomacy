import api from "./api";

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
