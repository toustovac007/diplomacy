import api from "./api";

const base = (gameId) => `games/${gameId}/draw-proposals/`;
export const getCurrentDraw = (gameId, signal) => api.get(`${base(gameId)}current/`, { signal }).then((r) => r.data);
export const proposeDraw = (gameId, participantIds) => api.post(base(gameId), { participant_ids: participantIds }).then((r) => r.data);
export const voteDraw = (gameId, id, vote) => api.post(`${base(gameId)}${id}/vote/`, { vote }).then((r) => r.data);
export const cancelDraw = (gameId, id) => api.post(`${base(gameId)}${id}/cancel/`).then((r) => r.data);
