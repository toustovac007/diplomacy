import { useEffect, useState } from "react";
import api from "../services/api";

const fields = [
    ["email_phase_started", "Nová herní fáze"],
    ["email_deadline_reminder", "Blížící se deadline"],
    ["email_chat_message", "Nové zprávy v chatu"],
    ["email_draw_events", "Hlasování o ukončení hry"],
    ["email_game_finished", "Konec hry"],
];

export default function NotificationSettings() {
    const [preferences, setPreferences] = useState(null);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const [message, setMessage] = useState("");
    const [attempt, setAttempt] = useState(0);
    useEffect(() => {
        const controller = new AbortController();
        api.get("notifications/preferences/", { signal: controller.signal })
            .then(({ data }) => { setPreferences(data); setError(""); })
            .catch(() => { if (!controller.signal.aborted) setError("Nastavení se nepodařilo načíst."); });
        return () => controller.abort();
    }, [attempt]);

    const save = async (event) => {
        event.preventDefault();
        if (busy) return;
        setBusy(true); setError(""); setMessage("");
        try {
            const response = await api.patch("notifications/preferences/", preferences);
            setPreferences(response.data);
            setMessage("Nastavení bylo uloženo.");
        } catch { setError("Nastavení se nepodařilo uložit. Zkus to znovu."); }
        finally { setBusy(false); }
    };
    return <section className="notification-settings" aria-labelledby="notification-settings-title">
        <h2 id="notification-settings-title">E-mailová upozornění</h2>
        {error && <p role="alert">{error}</p>}
        {message && <p role="status">{message}</p>}
        {!preferences ? <>{error ? <button onClick={() => setAttempt(attempt + 1)}>Zkusit znovu</button> : <p>Načítám nastavení…</p>}</>
            : <form onSubmit={save}>
                <fieldset disabled={busy}><legend>Posílat e-mailem</legend>
                    {fields.map(([field, label]) => <label key={field}>
                        <input type="checkbox" checked={preferences[field]} onChange={(event) => {
                            setPreferences({ ...preferences, [field]: event.target.checked }); setMessage("");
                        }} /> {label}
                    </label>)}
                    <button type="submit">{busy ? "Ukládám…" : "Uložit"}</button>
                </fieldset>
            </form>}
    </section>;
}
