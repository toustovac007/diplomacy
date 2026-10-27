import { useState } from "react";
import { useAuth } from "../context/AuthContext";

function Register({ onBackToLogin }) {
    const { register } = useAuth();

    const [username, setUsername] = useState("");
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [passwordAgain, setPasswordAgain] = useState("");
    const [error, setError] = useState("");

    const handleRegister = async (event) => {
        event.preventDefault();
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
            await register(username, email, password);
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
        }
    };

    return (
        <div>
            <h1>Diplomacy</h1>
            <h2>Registrace</h2>

            <form onSubmit={handleRegister}>
                <div>
                    <label>Uživatelské jméno</label>
                    <br />

                    <input
                        type="text"
                        value={username}
                        onChange={(event) => setUsername(event.target.value)}
                        required
                    />
                </div>

                <div>
                    <label>E-mail</label>
                    <br />

                    <input
                        type="email"
                        value={email}
                        onChange={(event) => setEmail(event.target.value)}
                        required
                    />
                </div>

                <div>
                    <label>Heslo</label>
                    <br />

                    <input
                        type="password"
                        value={password}
                        onChange={(event) => setPassword(event.target.value)}
                        required
                    />
                </div>

                <div>
                    <label>Heslo znovu</label>
                    <br />

                    <input
                        type="password"
                        value={passwordAgain}
                        onChange={(event) => setPasswordAgain(event.target.value)}
                        required
                    />
                </div>

                <button type="submit">
                    Vytvořit účet
                </button>
            </form>

            {error && <p>{error}</p>}

            <button onClick={onBackToLogin}>
                Zpět na přihlášení
            </button>
        </div>
    );
}

export default Register;