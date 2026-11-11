import api from "./api";

export async function getGameHistory(gameId, signal) {
    return (await api.get(`games/${gameId}/history/`, { signal })).data;
}

export async function getGameHistoryPhase(gameId, phaseId, signal) {
    return (await api.get(`games/${gameId}/history/${phaseId}/`, { signal })).data;
}
