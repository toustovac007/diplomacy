import { test } from "node:test";
import assert from "node:assert/strict";
import { conversationName, mergeMessages, nextCursor } from "./chatUtils.js";

test("polling and older pages merge once in chronological order", () => {
    const messages = mergeMessages([{ id: 51 }, { id: 52 }], [{ id: 53 }, { id: 52 }]);
    assert.deepEqual(mergeMessages(messages, [{ id: 51 }, { id: 50 }]).map((m) => m.id), [50, 51, 52, 53]);
});

test("cursor is extracted without following the API URL", () => {
    assert.equal(nextCursor({ next: "http://127.0.0.1:8000/api/games/1/chats/2/messages/?cursor=YWJj%3D" }), "YWJj=");
    assert.equal(nextCursor({ next: null }), null);
});

test("conversation names identify the other player and untitled groups", () => {
    const participants = [{ id: 1, username: "france", country_name: "Francie" }, { id: 2, username: "england", country_name: "Anglie" }];
    assert.equal(conversationName({ conversation_type: "direct", participants }, 1), "Anglie — england");
    assert.equal(conversationName({ conversation_type: "group", title: "Aliance", participants }, 1), "Aliance");
    assert.equal(conversationName({ conversation_type: "group", title: "", participants }, 1), "Francie, Anglie");
});
