import { useEffect, useState } from "react";
import api from "../services/api";

export default function VerificationRequest({ initialEmail = "" }) {
    const [email, setEmail] = useState(initialEmail);
    const [busy, setBusy] = useState(false);
    const [message, setMessage] = useState("");
    const [error, setError] = useState("");
    const [until, setUntil] = useState(0);
    const [remaining, setRemaining] = useState(0);
    useEffect(() => {
        if (!until) return;
        const update = () => setRemaining(Math.max(0, Math.ceil((until - Date.now()) / 1000)));
        update();
        const timer = setInterval(update, 1000);
        return () => clearInterval(timer);
    }, [until]);
    const send = async (event) => {
        event.preventDefault();
        if (busy || remaining) return;
        setBusy(true);
        setError("");
        setMessage("");
        try {
            const { data } = await api.post("users/email/verification/request/", { email }, { timeout: 15000 });
            setMessage(data.detail);
            setRemaining(60);
            setUntil(Date.now() + 60000);
        } catch (failure) {
            if (failure.response?.status === 429) {
                setError("Příliš mnoho žádostí. Zkuste to prosím později.");
                const delay = Math.max(60, Math.min(3600, Number(failure.response.headers?.["retry-after"]) || 60));
                setRemaining(delay);
                setUntil(Date.now() + delay * 1000);
            } else {
                setError("Žádost se nepodařilo odeslat. Zkontrolujte adresu a zkuste to znovu.");
            }
        } finally { setBusy(false); }
    };
    return <section aria-label="Zaslání ověřovacího e-mailu">
        <p>Pro používání účtu nejdřív ověřte svůj e-mail. Zkontrolujte doručenou poštu i spam.</p>
        <form className="login-form" onSubmit={send}>
            <div className="login-field">
                <label htmlFor="verification-email">E-mail účtu</label>
                <input id="verification-email" name="email" type="email" autoComplete="email"
                    required value={email} onChange={(event) => setEmail(event.target.value)} />
            </div>
            <button className="login-submit" disabled={busy || remaining > 0} type="submit">
                {busy ? "Odesílám..." : remaining ? `Další žádost za ${remaining} s` : "Zaslat ověřovací e-mail"}
            </button>
        </form>
        {message && <p role="status">{message}</p>}
        {error && <p className="login-error" role="alert">{error}</p>}
    </section>;
}
