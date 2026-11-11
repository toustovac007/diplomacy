export function mergeMessages(existing, incoming) {
    return [...new Map([...existing, ...incoming].map((message) => [message.id, message])).values()]
        .sort((a, b) => a.id - b.id);
}

export function nextCursor(page) {
    return page.next ? new URL(page.next, "http://localhost").searchParams.get("cursor") : null;
}

export function conversationName(conversation, playerId) {
    if (conversation.conversation_type === "direct") {
        const other = conversation.participants.find((player) => player.id !== playerId);
        return other ? `${other.country_name || other.country || "Hráč"} — ${other.username}` : "Přímý chat";
    }
    return conversation.title || conversation.participants.map((player) => player.country_name || player.username).join(", ");
}

export function chatError(error) {
    const data = error.response?.data;
    if (data?.detail) return data.detail;
    if (data && typeof data === "object") return Object.values(data).flat().join(" ");
    return "Zprávy se nepodařilo načíst nebo uložit. Zkus to prosím znovu.";
}
