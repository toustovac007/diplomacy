import { useEffect, useRef, useState } from "react";
import api from "../services/api";
import VerificationRequest from "../components/VerificationRequest";
import "./login.css";

export default function VerifyEmail() {
    const [token] = useState(() => new URLSearchParams(window.location.hash.slice(1)).get("token") || "");
    const [status, setStatus] = useState("ready");
    const [error, setError] = useState("");
    const flight = useRef(false);
    useEffect(() => {
        // Reading/opening the link does not consume it, including in StrictMode.
        window.history.replaceState(window.history.state, "", "/verify-email");
    }, []);
    const confirm = async () => {
        if (flight.current) return;
        flight.current = true;
        setStatus("working");
        setError("");
        try {
            await api.post("users/email/verification/confirm/", { token }, { timeout: 15000 });
            setStatus("verified");
        } catch (failure) {
            if (failure.response?.status === 400) {
                setStatus("invalid");
                setError("Odkaz vypršel, už byl použit nebo není platný. Pokud jste adresu již ověřili, přihlaste se. Jinak požádejte o nový odkaz.");
            } else {
                setStatus("ready");
                setError(failure.response?.status === 429 ? "Příliš mnoho pokusů. Zkuste to později."
                    : "Ověření se nepodařilo dokončit. Zkontrolujte připojení a zkuste to znovu.");
            }
        } finally { flight.current = false; }
    };
    return <main className="login-page">
        <section className="login-card" aria-labelledby="verify-title">
            <h1 id="verify-title">Ověření e-mailu</h1>
            {status === "verified" ? <p role="status">E-mail byl ověřen. Nyní se můžete přihlásit.</p> : <>
                {token && status !== "invalid" && <>
                    <p>Pokud jste požádali o ověření svého účtu Diplomacie, potvrďte svou e-mailovou adresu.</p>
                    <button className="login-submit" type="button" disabled={status === "working"} onClick={confirm}>
                        {status === "working" ? "Ověřuji..." : "Potvrdit ověření e-mailu"}
                    </button>
                </>}
                {error && <p className="login-error" role="alert">{error}</p>}
                {(!token || status === "invalid") && <VerificationRequest />}
            </>}
            <p className="login-register"><a href="/">Zpět na přihlášení</a></p>
        </section>
    </main>;
}
