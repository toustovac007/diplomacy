import { useEffect, useEffectEvent, useRef, useState } from "react";
import api from "../../services/api";

export default function PhaseReadinessPanel({ gameId, phaseId, orders, onChange, onPhaseChange }) {
    const [data, setData] = useState(null);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const requests = useRef(null);
    const publish = useEffectEvent((value, pending = false) => onChange({ ...value, pending }));
    const phaseChanged = useEffectEvent(() => onPhaseChange());

    useEffect(() => {
        const controller = new AbortController();
        let running = false;
        let queuedReady;
        let terminal = false;
        let current = null;
        async function request(ready) {
            if (terminal || controller.signal.aborted) return;
            const changing = typeof ready === "boolean";
            if (running) {
                // A click during a slow poll must not silently disappear.
                if (changing && queuedReady === undefined) {
                    queuedReady = ready;
                    setBusy(true);
                    publish(current, true);
                }
                return;
            }
            running = true;
            if (changing) { setBusy(true); publish(current, true); }
            try {
                const url = `games/${gameId}/readiness/`;
                const config = { signal: controller.signal };
                const response = changing ? await api.post(url, { ready }, config) : await api.get(url, config);
                if (controller.signal.aborted) return;
                current = response.data;
                setData(current);
                setError("");
                publish(current);
                if (current.phase_resolved || current.phase?.id !== phaseId || current.game_status !== "active") {
                    // Keep polling if parent reload fails; stop only on terminal game status.
                    await phaseChanged();
                    terminal = current.game_status === "finished";
                }
            } catch (failure) {
                if (!controller.signal.aborted) {
                    setError(failure.response?.data?.detail || "Připravenost se nepodařilo aktualizovat.");
                    publish(current);
                }
            } finally {
                running = false;
                if (!controller.signal.aborted) setBusy(false);
                if (queuedReady !== undefined) {
                    const next = queuedReady;
                    queuedReady = undefined;
                    // Never apply a queued click to a different/new phase.
                    if (current?.phase?.id === phaseId && !current.phase_resolved) request(next);
                }
            }
        }
        requests.current = request;
        request();
        const timer = setInterval(() => request(), 10000);
        return () => { controller.abort(); clearInterval(timer); requests.current = null; };
    }, [gameId, phaseId]);

    // Refresh own missing-order/build counts after an order save or cancellation.
    useEffect(() => { requests.current?.(); }, [orders]);

    return <section className="card phase-readiness" aria-label="Připravenost hráčů">
        <h3>Rozkazy hotové</h3>
        {error && <p role="alert">{error}</p>}
        {!data ? <p>Načítám připravenost…</p> : data.phase?.id === phaseId && <>
            {!data.readiness_supported ? <p>Ústupová fáze se ukončí automaticky po zadání rozhodnutí pro všechny vytlačené jednotky.</p> : <>
                <p>Připravenost hráčů: {data.ready_count} / {data.required_count} připraveno</p>
                {!data.is_required ? <p>V této fázi nemáš žádné rozkazy k zadání.</p> : <>
                    {data.is_ready ? <p>✓ Rozkazy označeny jako hotové.</p> : <>
                        {data.missing_order_count > 0 && <p>{data.missing_order_count} jednotky nemají rozkaz. Při vyhodnocení budou držet pozici (HOLD).</p>}
                        {data.builds_remaining > 0 && <p>Ještě můžeš postavit {data.builds_remaining} jednotek. Potvrzením připravenosti nevyužité stavby propadnou při vyhodnocení fáze.</p>}
                        {data.disbands_remaining > 0 && <p>Nejdřív zadej všechny povinné DISBAND rozkazy.</p>}
                    </>}
                    <button type="button" disabled={busy || (!data.is_ready && data.disbands_remaining > 0)}
                        onClick={() => requests.current?.(!data.is_ready)}>
                        {busy ? "Ukládám…" : data.is_ready ? "Znovu upravovat rozkazy" : "Označit rozkazy jako hotové"}
                    </button>
                </>}
            </>}
        </>}
    </section>;
}
