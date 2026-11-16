import { useState } from "react";
import { useAuth } from "../context/AuthContext";
import SocialLogin from "../components/SocialLogin";
import leftArtwork from "../assets/auth/login-left.png";
import rightArtwork from "../assets/auth/login-right.png";
import diplomacyMark from "../assets/auth/diplomacie-mark.png";
import "./login.css";

function Login({ onRegisterClick }) {
    const { login } = useAuth();

    const [username, setUsername] = useState("");
    const [password, setPassword] = useState("");
    const [error, setError] = useState("");

    const handleLogin = async (event) => {
        event.preventDefault();
        setError("");

        try {
            await login(username, password);
        } catch (error) {
            console.error("Authentication request failed", error.response?.status);

            if (error.response?.status === 401) {
                setError("Nesprávné uživatelské jméno nebo heslo.");
            } else {
                setError("Nastala chyba při přihlašování.");
            }
        }
    };

    return (
        <main className="login-page">
            <div className="login-artwork" aria-hidden="true">
                <img className="login-artwork__left" src={leftArtwork} alt="" />
                <img className="login-artwork__right" src={rightArtwork} alt="" />
            </div>
            <section className="login-card" aria-labelledby="login-title">
                <header className="login-card__header">
                    <img className="login-mark" src={diplomacyMark} alt="" />
                    <h1 id="login-title">Diplomacie</h1>
                    <p>Strategické aliance, vyjednávání a boj o nadvládu v Evropě.</p>
                </header>
                <h2>Přihlášení</h2>

                <form className="login-form" onSubmit={handleLogin}>
                    <div className="login-field">
                        <label htmlFor="login-username">Uživatelské jméno</label>
                        <input
                            id="login-username"
                            name="username"
                            autoComplete="username"
                            type="text"
                            value={username}
                            onChange={(event) => setUsername(event.target.value)}
                        />
                    </div>

                    <div className="login-field">
                        <label htmlFor="login-password">Heslo</label>
                        <input
                            id="login-password"
                            name="password"
                            autoComplete="current-password"
                            type="password"
                            value={password}
                            onChange={(event) => setPassword(event.target.value)}
                        />
                    </div>

                    <button className="login-submit" type="submit">
                        Přihlásit
                    </button>
                </form>

                {error && <p className="login-error" role="alert">{error}</p>}
                <SocialLogin />

                <p className="login-register">
                    Nemáte ještě účet?{" "}
                    <button type="button" onClick={onRegisterClick}>Registrovat</button>
                </p>
            </section>
        </main>
    );
}

export default Login;
