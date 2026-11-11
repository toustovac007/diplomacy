import { Fragment, useCallback, useEffect, useEffectEvent, useLayoutEffect, useRef, useState } from "react";
import { createConversation, getConversations, getMessages, markConversationRead, sendMessage } from "../../services/chat";
import { COUNTRY_COLORS } from "./countryColors";
import { chatError, conversationName, mergeMessages, nextCursor } from "./chatUtils";

function ChatThread({ gameId, conversation, currentPlayer, active, onRead, visible }) {
    const [messages, setMessages] = useState([]);
    const [cursor, setCursor] = useState(null);
    const [loading, setLoading] = useState(true);
    const [loadingOlder, setLoadingOlder] = useState(false);
    const [error, setError] = useState("");
    const [text, setText] = useState("");
    const [sending, setSending] = useState(false);
    const history = useRef([]);
    const scrollBox = useRef(null);
    const scrollPlan = useRef(null);
    const loadRef = useRef(null);
    const sendBusy = useRef(false);
    const alive = useRef(false);
    const conversationId = conversation.id;
    const isPanelVisible = useEffectEvent(() => visible);

    useLayoutEffect(() => {
        const box = scrollBox.current;
        const plan = scrollPlan.current;
        if (box && plan) {
            box.scrollTop = plan === "bottom" ? box.scrollHeight : plan.top + box.scrollHeight - plan.height;
            scrollPlan.current = null;
        }
    }, [messages]);

    useEffect(() => {
        alive.current = true;
        let disposed = false;
        let busy = false;
        let olderCursor = null;
        let lastFetchedId = null;
        const controller = new AbortController();
        const load = async (older = false) => {
            if (busy || disposed || document.visibilityState === "hidden" || (older && !olderCursor)) return;
            busy = true;
            if (older) setLoadingOlder(true);
            try {
                let page = await getMessages(gameId, conversationId, older ? olderCursor : null, controller.signal);
                let incoming = page.results;
                // Catch up to the known history even if more than one page arrived
                // between polls. Initial opening still fetches just 50 messages.
                const known = new Set(history.current.map((message) => message.id));
                while (!older && lastFetchedId !== null && page.next && page.results.every((message) => message.id > lastFetchedId)) {
                    page = await getMessages(gameId, conversationId, nextCursor(page), controller.signal);
                    incoming = [...incoming, ...page.results];
                }
                if (disposed) return;
                if (older || lastFetchedId === null) {
                    olderCursor = nextCursor(page);
                    setCursor(olderCursor);
                }
                if (!older) lastFetchedId = incoming[0]?.id ?? 0;
                const box = scrollBox.current;
                const hasNew = incoming.some((message) => !known.has(message.id));
                if (hasNew) {
                    if (older && box) scrollPlan.current = { top: box.scrollTop, height: box.scrollHeight };
                    else if (!known.size || (box && box.scrollHeight - box.scrollTop - box.clientHeight < 60)) scrollPlan.current = "bottom";
                    history.current = mergeMessages(history.current, incoming);
                    setMessages(history.current);
                }
                setError("");
                setLoading(false);
                if (!older && document.visibilityState === "visible" && isPanelVisible()) {
                    await markConversationRead(gameId, conversationId, controller.signal);
                    if (!disposed) onRead(conversationId);
                }
            } catch (err) {
                if (!disposed) setError(chatError(err));
            } finally {
                busy = false;
                if (!disposed) { setLoading(false); setLoadingOlder(false); }
            }
        };
        loadRef.current = load;
        void load();
        const timer = setInterval(() => { void load(); }, 5000);
        const visible = () => { if (document.visibilityState === "visible") void load(); };
        document.addEventListener("visibilitychange", visible);
        return () => {
            disposed = true;
            alive.current = false;
            controller.abort();
            clearInterval(timer);
            document.removeEventListener("visibilitychange", visible);
            loadRef.current = null;
        };
    }, [gameId, conversationId, onRead]);

    useEffect(() => {
        if (visible) void loadRef.current?.();
    }, [visible]);

    const submit = async (event) => {
        event.preventDefault();
        if (!active || sendBusy.current || !text.trim() || text.length > 4000) return;
        sendBusy.current = true;
        setSending(true);
        setError("");
        try {
            const message = await sendMessage(gameId, conversationId, text);
            if (!alive.current) return;
            setText("");
            scrollPlan.current = "bottom";
            history.current = mergeMessages(history.current, [message]);
            setMessages(history.current);
            void loadRef.current?.();
        } catch (err) {
            if (alive.current) setError(chatError(err));
        } finally {
            sendBusy.current = false;
            if (alive.current) setSending(false);
        }
    };

    return <section className="chat-thread" aria-label="Zprávy konverzace">
        <h3>{conversationName(conversation, currentPlayer.id)}</h3>
        <p className="chat-participants">{conversation.participants.map((p) => `${p.country_name || "Hráč"} — ${p.username}`).join(", ")}</p>
        {error && <p role="alert">{error}</p>}
        <div className="chat-history" ref={scrollBox} aria-label="Historie zpráv" tabIndex={0}>
            {cursor && <button type="button" disabled={loadingOlder} onClick={() => loadRef.current?.(true)}>
                {loadingOlder ? "Načítám…" : "Načíst starší zprávy"}
            </button>}
            {loading ? <p>Načítám zprávy…</p> : !messages.length && <p>Zatím žádné zprávy.</p>}
            {messages.map((message, index) => <Fragment key={message.id}>
                {(index === 0 || messages[index - 1].phase?.id !== message.phase?.id) && <p className="chat-phase">
                    {message.phase ? `${message.phase.season_name} ${message.phase.year} · ${message.phase.phase_type_name}` : "Bez fáze"}
                </p>}
                <article className={`chat-message ${message.sender === currentPlayer.id ? "chat-own" : ""}`}
                    style={{ "--chat-country": COUNTRY_COLORS[message.sender_country] || "var(--border)" }}>
                    <strong>{message.sender_country_name || "Hráč"} — {message.sender_username}</strong>
                    <p className="chat-text">{message.text}</p>
                    <time dateTime={message.created_at}>{new Date(message.created_at).toLocaleString("cs-CZ")}</time>
                </article>
            </Fragment>)}
        </div>
        {active ? <form onSubmit={submit} className="chat-compose">
            <label htmlFor={`chat-text-${conversationId}`}>Zpráva</label>
            <textarea id={`chat-text-${conversationId}`} value={text} disabled={sending || loading} rows={3}
                onChange={(event) => setText(event.target.value)}
                onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) submit(event);
                }} />
            <span>{text.length} / 4000 · Shift+Enter pro nový řádek</span>
            <button type="submit" disabled={sending || !text.trim() || text.length > 4000}>{sending ? "Odesílám…" : "Odeslat"}</button>
        </form> : <p>Hra je ukončena. Zprávy jsou pouze ke čtení.</p>}
    </section>;
}

export default function GameChat({ game, currentPlayer, visible = true, onUnreadCountChange }) {
    const [conversations, setConversations] = useState([]);
    const [selected, setSelected] = useState(null);
    const [creating, setCreating] = useState(false);
    const [participants, setParticipants] = useState([]);
    const [title, setTitle] = useState("");
    const [busy, setBusy] = useState(false);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const unreadCount = conversations.reduce((total, item) => total + (item.unread_count ?? 0), 0);
    useEffect(() => { onUnreadCountChange?.(unreadCount); }, [unreadCount, onUnreadCountChange]);
    const active = game.status === "active";
    const gameId = game.id;
    const listVersion = useRef(0);

    useEffect(() => {
        let disposed = false;
        let pending = false;
        const controller = new AbortController();
        const load = async () => {
            if (pending || document.visibilityState === "hidden") return;
            pending = true;
            const version = listVersion.current;
            try {
                const data = await getConversations(gameId, controller.signal);
                if (!disposed && version === listVersion.current) { setConversations(data); setError(""); }
            } catch (err) {
                if (!disposed) setError(chatError(err));
            } finally {
                pending = false;
                if (!disposed) setLoading(false);
            }
        };
        void load();
        const timer = setInterval(() => { void load(); }, 10000);
        const visible = () => { if (document.visibilityState === "visible") void load(); };
        document.addEventListener("visibilitychange", visible);
        return () => { disposed = true; controller.abort(); clearInterval(timer); document.removeEventListener("visibilitychange", visible); };
    }, [gameId]);

    const onRead = useCallback((id) => {
        setConversations((items) => items.map((item) => item.id === id ? { ...item, unread_count: 0 } : item));
    }, []);

    const create = async (event) => {
        event.preventDefault();
        if (busy || !participants.length || !active) return;
        setBusy(true);
        setError("");
        try {
            const conversation = await createConversation(gameId, {
                conversation_type: participants.length === 1 ? "direct" : "group",
                participant_ids: participants, title: participants.length > 1 ? title : "",
            });
            listVersion.current += 1;
            setConversations((items) => [conversation, ...items.filter((item) => item.id !== conversation.id)]);
            setSelected(conversation.id);
            setCreating(false); setParticipants([]); setTitle("");
        } catch (err) { setError(chatError(err)); }
        finally { setBusy(false); }
    };
    const selectedConversation = conversations.find((item) => item.id === selected);

    return <section className="game-chat" aria-label="Diplomacie a zprávy">
        <h2>Diplomacie / Zprávy</h2>
        {error && <p role="alert">{error}</p>}
        <div className="chat-layout">
            <aside className="chat-sidebar" aria-label="Konverzace">
                {active && <button type="button" onClick={() => setCreating(!creating)}>Nový chat</button>}
                {active && creating && <form onSubmit={create} className="chat-create">
                    <fieldset disabled={busy}><legend>Vyber spoluhráče</legend>
                        {game.players.filter((player) => player.id !== currentPlayer.id).map((player) => <label key={player.id}>
                            <input type="checkbox" checked={participants.includes(player.id)} onChange={(event) =>
                                setParticipants(event.target.checked ? [...participants, player.id] : participants.filter((id) => id !== player.id))} />
                            {player.country_name} — {player.username}
                        </label>)}
                        {participants.length > 1 && <label>Název skupiny (volitelný)
                            <input value={title} maxLength={100} onChange={(event) => setTitle(event.target.value)} />
                        </label>}
                        <button type="submit" disabled={!participants.length || busy}>{busy ? "Otevírám…" : "Otevřít chat"}</button>
                    </fieldset>
                </form>}
                {loading && <p>Načítám konverzace…</p>}
                {!loading && !conversations.length && <p>Zatím žádné konverzace.</p>}
                <ul>{conversations.map((conversation) => <li key={conversation.id}>
                    <button type="button" aria-pressed={selected === conversation.id} onClick={() => setSelected(conversation.id)}>
                        <strong>{conversationName(conversation, currentPlayer.id)}</strong>
                        {conversation.unread_count > 0 && <span className="chat-unread">{conversation.unread_count} nepřečtených</span>}
                        {conversation.last_message && <span className="chat-preview">{conversation.last_message.text}</span>}
                    </button>
                </li>)}</ul>
            </aside>
            {selectedConversation ? <ChatThread key={selectedConversation.id} gameId={gameId} conversation={selectedConversation}
                currentPlayer={currentPlayer} active={active} onRead={onRead} visible={visible} /> : <p>Vyber konverzaci.
                {!active && " Hra je ukončena. Zprávy jsou pouze ke čtení."}</p>}
        </div>
    </section>;
}
