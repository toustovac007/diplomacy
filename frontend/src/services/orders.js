import api from "./api";


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