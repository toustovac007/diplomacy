import { useState } from "react";
import { useAuth } from "../context/AuthContext";
import VerificationRequest from "../components/VerificationRequest";
import leftArtwork from "../assets/auth/login-left.png";
import rightArtwork from "../assets/auth/login-right.png";
import "./login.css";

function Register({ onBackToLogin }) {
    const { register } = useAuth();

    const [username, setUsername] = useState("");
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [passwordAgain, setPasswordAgain] = useState("");
    const [error, setError] = useState("");
    const [busy, setBusy] = useState(false);
    const [submitted, setSubmitted] = useState(false);

    const handleRegister = async (event) => {
        event.preventDefault();
        if (busy) return;
        setError("");

        if (password !== passwordAgain) {
            setError("Hesla se neshodují.");
            return;
        }

        if (password.length < 8) {
            setError("Heslo musí mít alespoň 8 znaků.");
            return;
        }

        try {
            setBusy(true);
            await register(username, email, password);
            setSubmitted(true);
            setPassword("");
            setPasswordAgain("");
        } catch (error) {
            console.error("Authentication request failed", error.response?.status);

            if (error.response?.data?.username) {
                setError("Toto uživatelské jméno už existuje.");
            } else if (error.response?.data?.email) {
                setError("Tento e-mail už je zaregistrovaný.");
            } else if (error.response?.data?.password) {
                setError("Heslo není platné.");
            } else {
                setError("Registrace se nepodařila.");
            }
        } finally { setBusy(false); }
    };

    return (
        <main className="login-page">
            <div className="login-artwork" aria-hidden="true">
                <img className="login-artwork__left" src={leftArtwork} alt="" />
                <img className="login-artwork__right" src={rightArtwork} alt="" />
            </div>
            <section className="login-card" aria-labelledby="register-title">
                <header className="login-card__header">
                    <img className="login-mark" src="/diplomacie-mark.svg" width="128" height="128" alt="" />
                    <h1 id="register-title">Diplomacie</h1>
                </header>
                <h2>{submitted ? "Ověřte svůj e-mail" : "Vytvoření účtu"}</h2>

                {submitted ? <VerificationRequest initialEmail={email} /> : <form className="login-form" onSubmit={handleRegister}>
                    <div className="login-field">
                        <label htmlFor="register-username">Uživatelské jméno</label>
                        <input
                            id="register-username"
                            maxLength={32}
                            name="username"
                            autoComplete="username"
                            type="text"
                            value={username}
                            onChange={(event) => setUsername(event.target.value)}
                            required
                        />
                    </div>

                    <div className="login-field">
                        <label htmlFor="register-email">E-mail</label>
                        <input
                            id="register-email"
                            name="email"
                            autoComplete="email"
                            type="email"
                            value={email}
                            onChange={(event) => setEmail(event.target.value)}
                            required
                        />
                    </div>

                    <div className="login-field">
                        <label htmlFor="register-password">Heslo</label>
                        <input
                            id="register-password"
                            name="password"
                            autoComplete="new-password"
                            type="password"
                            value={password}
                            onChange={(event) => setPassword(event.target.value)}
                            required
                        />
                    </div>

                    <div className="login-field">
                        <label htmlFor="register-passwordAgain">Heslo znovu</label>
                        <input
                            id="register-passwordAgain"
                            name="passwordAgain"
                            autoComplete="new-password"
                            type="password"
                            value={passwordAgain}
                            onChange={(event) => setPasswordAgain(event.target.value)}
                            required
                        />
                    </div>

                    <button className="login-submit" type="submit" disabled={busy}>
                        {busy ? "Odesílám..." : "Vytvořit účet"}
                    </button>
                </form>}

                {error && <p className="login-error" role="alert">{error}</p>}

                <p className="login-register">
                    Už máte účet?{" "}
                    <button type="button" onClick={onBackToLogin}>Přihlásit se</button>
                </p>
            </section>
        </main>
    );
}

export default Register;
