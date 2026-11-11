import { useEffect, useEffectEvent, useRef, useState } from "react";
import { cancelDraw, getCurrentDraw, proposeDraw, voteDraw } from "../../services/draws";

const playerName = (player) => `${player.country_name || player.country} — ${player.username}`;

export default function DrawProposalPanel({ gameId, currentPlayer, onGameFinished }) {
    const [data, setData] = useState(null);
    const [editing, setEditing] = useState(false);
    const [selected, setSelected] = useState([currentPlayer.id]);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const [message, setMessage] = useState("");
    const inFlight = useRef(false);
    const version = useRef(0);
    const pollFinished = useEffectEvent(() => onGameFinished());

    useEffect(() => {
        let disposed = false;
        let polling = false;
        const controller = new AbortController();
        const load = async () => {
            if (polling || inFlight.current || document.visibilityState === "hidden") return;
            polling = true;
            const requestVersion = version.current;
            try {
                const response = await getCurrentDraw(gameId, controller.signal);
                if (disposed || requestVersion !== version.current) return;
                setData(response);
                if (response.game_status === "finished") {
                    await pollFinished();
                }
            } catch (err) {
                if (!disposed) setError(err.response?.data?.detail || "Návrh se nepodařilo načíst.");
            } finally { polling = false; }
        };
        void load();
        const timer = setInterval(() => { void load(); }, 10000);
        return () => { disposed = true; controller.abort(); clearInterval(timer); };
    }, [gameId]);

    const act = async (request) => {
        if (inFlight.current) return;
        inFlight.current = true;
        version.current += 1;
        setBusy(true); setError(""); setMessage("");
        try {
            const response = await request();
            setData((previous) => ({ ...previous, ...response, proposal: response.proposal?.status === "open" ? response.proposal : null }));
            setEditing(false);
            setSelected([currentPlayer.id]);
            if (response.game_status === "finished") await onGameFinished();
            else if (response.proposal?.status === "rejected") setMessage("Návrh byl zamítnut. Hra pokračuje.");
            else if (response.proposal?.status === "cancelled") setMessage("Návrh byl zrušen. Hra pokračuje.");
        } catch (err) {
            setError(err.response?.data?.detail || "Akci se nepodařilo uložit. Zkus to prosím znovu.");
        } finally { inFlight.current = false; setBusy(false); }
    };

    const proposal = data?.proposal;
    const isProposer = proposal?.proposer.id === currentPlayer.id;
    const survivors = data?.surviving_players ?? [];
    const canPropose = survivors.some((player) => player.id === currentPlayer.id);
    const ballot = proposal?.voters.find(({ player }) => player.id === currentPlayer.id);
    const validSelected = selected.filter((id) => survivors.some((player) => player.id === id));

    return <section className="draw-panel" aria-labelledby="draw-title">
        <h2 id="draw-title">Dohoda o ukončení hry</h2>
        {error && <p role="alert">{error}</p>}
        {message && <p role="status">{message}</p>}
        {!data ? <p>Načítám návrh…</p> : proposal ? <>
            <h3>Návrh sdíleného vítězství</h3>
            <p>Navrhl: {playerName(proposal.proposer)}</p>
            <p>Navržení vítězové: {proposal.participants.map(playerName).join(", ")}</p>
            <p>Souhlas je nutný od všech hráčů uvedených níže, včetně těch mimo navržené vítěze.</p>
            <ul>{proposal.voters.map(({ player, vote }) => <li key={player.id}>
                {vote === "accept" ? "✓" : vote === "reject" ? "✗" : "?"} {playerName(player)} — {vote === "accept" ? "souhlasí" : vote === "reject" ? "nesouhlasí" : "čeká"}
            </li>)}</ul>
            <div className="draw-actions">
                {ballot && !isProposer && <>
                    <button disabled={busy} onClick={() => act(() => voteDraw(gameId, proposal.id, "accept"))}>Souhlasím</button>
                    <button disabled={busy} onClick={() => act(() => voteDraw(gameId, proposal.id, "reject"))}>Nesouhlasím</button>
                </>}
                {isProposer && <button disabled={busy} onClick={() => act(() => cancelDraw(gameId, proposal.id))}>Zrušit návrh</button>}
            </div>
        </> : canPropose ? <>
            <button disabled={busy} onClick={() => setEditing(!editing)}>Navrhnout sdílené vítězství</button>
            {editing && <form onSubmit={(event) => { event.preventDefault(); void act(() => proposeDraw(gameId, validSelected)); }}>
                <fieldset disabled={busy}><legend>Navržení vítězové</legend>
                    {survivors.map((player) => <label key={player.id}>
                        <input type="checkbox" checked={selected.includes(player.id)} disabled={player.id === currentPlayer.id}
                            onChange={(event) => setSelected(event.target.checked ? [...selected, player.id] : selected.filter((id) => id !== player.id))} />
                        {playerName(player)}
                    </label>)}
                    <button disabled={busy || validSelected.length < 2} type="submit">Navrhnout</button>
                </fieldset>
            </form>}
        </> : <p>Vyřazení hráči nemohou navrhovat dohodu. Otevřený návrh zde mohou sledovat.</p>}
    </section>;
}
