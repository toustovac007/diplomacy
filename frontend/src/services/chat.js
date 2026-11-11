import api from "./api";

const base = (gameId) => `games/${gameId}/chats/`;
export const getConversations = (gameId, signal) => api.get(base(gameId), { signal }).then((r) => r.data);
export const createConversation = (gameId, data) => api.post(base(gameId), data).then((r) => r.data);
export const getMessages = (gameId, conversationId, cursor, signal) =>
    api.get(`${base(gameId)}${conversationId}/messages/`, { params: cursor ? { cursor } : {}, signal }).then((r) => r.data);
export const sendMessage = (gameId, conversationId, text) =>
    api.post(`${base(gameId)}${conversationId}/messages/`, { text }).then((r) => r.data);
export const markConversationRead = (gameId, conversationId, signal) =>
    api.post(`${base(gameId)}${conversationId}/read/`, {}, { signal });
