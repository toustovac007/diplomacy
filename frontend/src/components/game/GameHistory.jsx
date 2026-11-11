import { useEffect, useState } from "react";
import { getGameHistory, getGameHistoryPhase } from "../../services/history";
import GameMap from "./GameMap";
import historicalOrderLabel from "./historicalOrderLabel";

const phaseLabel = (phase) => `${phase.season_name} ${phase.year} — ${phase.phase_type_name}`;

function HistoryPhase({ gameId, phaseId }) {
    const [data, setData] = useState(null);
    const [error, setError] = useState("");
    const [attempt, setAttempt] = useState(0);
    useEffect(() => {
        const controller = new AbortController();
        getGameHistoryPhase(gameId, phaseId, controller.signal)
            .then((result) => {
                if (!controller.signal.aborted) { setData(result); setError(""); }
            })
            .catch((err) => {
                if (!controller.signal.aborted) setError(err.response?.data?.detail || "Historii fáze se nepodařilo načíst.");
            });
        return () => controller.abort();
    }, [gameId, phaseId, attempt]);
    if (error) return <p role="alert">{error} <button onClick={() => setAttempt(attempt + 1)}>Zkusit znovu</button></p>;
    if (!data) return <p>Načítání fáze…</p>;
    return <>
        <h3>{phaseLabel(data.phase)}</h3>
        <p>Vyhodnoceno: {data.phase.resolved_at ? new Date(data.phase.resolved_at).toLocaleString("cs-CZ") : "—"}</p>
        {data.state_available
            ? <GameMap phaseType={data.phase.phase_type} units={data.state.units}
                supplyCenters={data.state.supply_centers} showHistoricalOrders
                historicalOrders={data.orders ?? []} />
            : <p>Historický stav mapy pro tuto fázi není k dispozici.</p>}
        {!data.orders_available ? <p>Historické rozkazy pro tuto fázi nejsou k dispozici.</p>
            : data.orders.length === 0 ? <p>Žádné rozkazy.</p>
                : <ul>{data.orders.map((order, index) => <li key={`${order.id}-${index}`}
                    style={{ color: order.result === "failed" ? "#b91c1c" : undefined }}>
                    {order.result === "failed" ? "✗" : "✓"} {order.country}: {historicalOrderLabel(order)}
                    {order.result === "failed" && order.result_reason && ` (${order.result_reason})`}
                </li>)}</ul>}
    </>;
}

function HistoryBrowser({ gameId }) {
    const [phases, setPhases] = useState(null);
    const [selectedId, setSelectedId] = useState(null);
    const [error, setError] = useState("");
    const [attempt, setAttempt] = useState(0);
    useEffect(() => {
        const controller = new AbortController();
        getGameHistory(gameId, controller.signal).then((data) => {
            if (controller.signal.aborted) return;
            setPhases(data.phases);
            setSelectedId(data.phases.at(-1)?.id ?? null);
            setError("");
        }).catch((err) => {
            if (!controller.signal.aborted) setError(err.response?.data?.detail || "Historii hry se nepodařilo načíst.");
        });
        return () => controller.abort();
    }, [gameId, attempt]);
    if (error) return <p role="alert">{error} <button onClick={() => setAttempt(attempt + 1)}>Zkusit znovu</button></p>;
    if (!phases) return <p>Načítání historie…</p>;
    if (!phases.length) return <p>Zatím nebyla vyhodnocena žádná fáze.</p>;
    const index = phases.findIndex((phase) => phase.id === selectedId);
    return <>
        <label>Fáze{" "}
            <select value={selectedId} onChange={(event) => setSelectedId(Number(event.target.value))}>
                {phases.map((phase) => <option key={phase.id} value={phase.id}>{phaseLabel(phase)}</option>)}
            </select>
        </label>{" "}
        <button disabled={index <= 0} onClick={() => setSelectedId(phases[index - 1].id)}>← Předchozí fáze</button>{" "}
        <button disabled={index >= phases.length - 1} onClick={() => setSelectedId(phases[index + 1].id)}>Další fáze →</button>
        <HistoryPhase key={selectedId} gameId={gameId} phaseId={selectedId} />
    </>;
}

export default function GameHistory({ gameId, embedded = false }) {
    const [open, setOpen] = useState(false);
    if (embedded) return <section aria-label="Historie hry"><HistoryBrowser gameId={gameId} /></section>;
    return <section aria-label="Historie hry">
        <button type="button" aria-expanded={open} onClick={() => setOpen(!open)}>
            {open ? "Skrýt historii hry" : "Historie hry"}
        </button>
        {open && <HistoryBrowser gameId={gameId} />}
    </section>;
}
