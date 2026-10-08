import { useState } from "react";
import { useAuth } from "../context/AuthContext";

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
            console.error(error);

            if (error.response?.status === 401) {
                setError("Nesprávné uživatelské jméno nebo heslo.");
            } else {
                setError("Nastala chyba při přihlašování.");
            }
        }
    };

    return (
        <div>
            <h1>Diplomacy</h1>
            <h2>Přihlášení</h2>

            <form onSubmit={handleLogin}>
                <div>
                    <label>Uživatelské jméno</label>
                    <br />
                    <input
                        type="text"
                        value={username}
                        onChange={(event) => setUsername(event.target.value)}
                    />
                </div>

                <div>
                    <label>Heslo</label>
                    <br />
                    <input
                        type="password"
                        value={password}
                        onChange={(event) => setPassword(event.target.value)}
                    />
                </div>

                <button type="submit">
                    Přihlásit
                </button>
            </form>

            {error && <p>{error}</p>}

             <p>Nemáš ještě účet?</p>

            <button onClick={onRegisterClick}>
                Vytvořit účet
            </button>
        </div>
    );
}

export default Login;