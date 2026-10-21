import { useEffect, useState } from "react";
import { useAuth } from "../context/AuthContext";
import api from "../services/api";
import { Link } from "react-router-dom";
import GameSettingsSummary from "../components/game/GameSettingsSummary";
import NotificationSettings from "../components/NotificationSettings";

const defaultSettings = {
    max_players: 7,
    is_public: true,
    movement_duration_minutes: 1440,
    retreat_duration_minutes: 720,
    adjustment_duration_minutes: 720,
};
const durationFields = [
    ["movement_duration_minutes", "Pohyby", [60, 360, 720, 1440, 2880, 4320]],
    ["retreat_duration_minutes", "Ústupy", [60, 360, 720, 1440]],
    ["adjustment_duration_minutes", "Zimní úpravy", [60, 360, 720, 1440]],
];
const fieldLabels = Object.fromEntries([
    ["name", "Název hry"], ["max_players", "Počet hráčů"], ["is_public", "Viditelnost"],
    ["invite_code", "Pozvánka"], ...durationFields.map(([field, label]) => [field, label]),
]);
function backendError(error, fallback) {
    const data = error.response?.data;
    if (!data || typeof data !== "object") return fallback;
    if (data.detail) return data.detail;
    return Object.entries(data).map(([field, messages]) =>
        `${fieldLabels[field] || field}: ${Array.isArray(messages) ? messages.join(" ") : messages}`
    ).join(" ") || fallback;
}


function Home() {
    const { user, logout } = useAuth();

    const [games, setGames] = useState([]);
    const [publicGames, setPublicGames] = useState([]);

    const [name, setName] = useState("");
    const [settings, setSettings] = useState(defaultSettings);
    const [inviteCode, setInviteCode] = useState("");

    const [error, setError] = useState("");
    const [message, setMessage] = useState("");


    const loadGames = async () => {
        try {
            const response = await api.get("games/");
            setGames(response.data);
        } catch (error) {
            console.error(error);
            setError("Nepodařilo se načíst tvoje hry.");
        }
    };


    const loadPublicGames = async () => {
        try {
            const response = await api.get("games/public/");
            setPublicGames(response.data);
        } catch (error) {
            console.error(error);
            setError("Nepodařilo se načíst veřejné hry.");
        }
    };


    const loadAllGames = async () => {
        await Promise.all([
            loadGames(),
            loadPublicGames(),
        ]);
    };


    useEffect(() => {
        loadAllGames();
    }, []);


    const handleCreateGame = async (event) => {
        event.preventDefault();

        setError("");
        setMessage("");

        if (!name.trim()) {
            setError("Zadej název hry.");
            return;
        }

        try {
            await api.post("games/", {
                name: name,
                ...settings,
            });

            setName("");
            setSettings(defaultSettings);

            setMessage("Hra byla vytvořena.");

            await loadAllGames();

        } catch (error) {
            console.error(error);
            setError(backendError(error, "Hru se nepodařilo vytvořit."));
        }
    };


    const handleJoinGame = async (gameId) => {
        setError("");
        setMessage("");

        try {
            await api.post(`games/${gameId}/join/`);

            setMessage("Úspěšně ses připojil ke hře.");

            await loadAllGames();

        } catch (error) {
            console.error(error);

            const backendMessage =
                error.response?.data?.detail;

            if (backendMessage) {
                setError(backendMessage);
            } else {
                setError("Ke hře se nepodařilo připojit.");
            }
        }
    };


    const handleJoinByCode = async (event) => {
        event.preventDefault();
        setError("");
        setMessage("");
        try {
            await api.post("games/join-by-code/", { invite_code: inviteCode.trim() });
            setInviteCode("");
            setMessage("Úspěšně ses připojil ke hře.");
            await loadAllGames();
        } catch (error) {
            setError(backendError(error, "Ke hře se nepodařilo připojit."));
        }
    };

    return (
        <div>
            <h1>Diplomacy</h1>

            <p>
                Přihlášen jako: <strong>{user?.username}</strong>
            </p>

            <button onClick={logout}>
                Odhlásit se
            </button>

            <hr />

            <NotificationSettings key={user?.username} />

            <h2>Vytvořit hru</h2>

            <form onSubmit={handleCreateGame}>
                <div>
                    <label>Název hry</label>
                    <br />

                    <input
                        type="text"
                        value={name}
                        onChange={(event) =>
                            setName(event.target.value)
                        }
                    />
                </div>

                <div>
                    <label htmlFor="max-players">Počet hráčů</label>{" "}
                    <select id="max-players" value={settings.max_players}
                        onChange={(event) => setSettings({ ...settings, max_players: Number(event.target.value) })}>
                        {[2, 3, 4, 5, 6, 7].map((count) => <option key={count} value={count}>{count}</option>)}
                    </select>
                </div>
                <div>
                    <label htmlFor="visibility">Viditelnost</label>{" "}
                    <select id="visibility" value={String(settings.is_public)}
                        onChange={(event) => setSettings({ ...settings, is_public: event.target.value === "true" })}>
                        <option value="true">Veřejná</option>
                        <option value="false">Soukromá</option>
                    </select>
                </div>
                {durationFields.map(([field, label, values]) => <div key={field}>
                    <label htmlFor={field}>{label}</label>{" "}
                    <select id={field} value={settings[field]}
                        onChange={(event) => setSettings({ ...settings, [field]: Number(event.target.value) })}>
                        {values.map((minutes) => <option key={minutes} value={minutes}>{minutes / 60} h</option>)}
                    </select>
                </div>)}

                <br />

                <button type="submit">
                    Vytvořit hru
                </button>
            </form>

            <h2>Připojit se pomocí pozvánky</h2>
            <form onSubmit={handleJoinByCode}>
                <label htmlFor="invite-code">Kód pozvánky</label>{" "}
                <input id="invite-code" value={inviteCode} required
                    onChange={(event) => setInviteCode(event.target.value)} />{" "}
                <button type="submit">Připojit se</button>
            </form>

            {error && (
                <p>{error}</p>
            )}

            {message && (
                <p>{message}</p>
            )}

            <hr />

            <h2>Moje hry</h2>

            {games.length === 0 ? (
                <p>Zatím nejsi v žádné hře.</p>
            ) : (
                <div>
                    {games.map((game) => (
                        <div key={game.id}>
                            <h3>
                                <Link to={`/games/${game.id}`}>
                                    {game.name}
                                </Link>
                            </h3>



                            <p>
                                Zakladatel: {game.creator}
                            </p>

                            {game.status === "finished" ? <div className="finished-game-summary">
                                <span className="finished-game-badge">✓ {game.result_type === "draw" ? "Dokončena — dohoda" : "Dokončena"}</span>
                                {game.result_type === "draw" ? <p>Sdílené vítězství: {(game.draw_participants ?? []).map((p) => p.country_name || p.country).join(", ")}</p>
                                    : game.winner && <p>Vítěz: <strong>{game.winner.country_name}</strong> — {game.winner.username}</p>}
                            </div> : <p>Stav: {game.status}</p>}

                            <GameSettingsSummary game={game} />

                            <p>
                                Hráči:
                            </p>

                            <ul>
                                {game.players.map((player) => (
                                    <li key={player.id}>
                                        {player.username}
                                    </li>
                                ))}
                            </ul>

                            <hr />
                        </div>
                    ))}
                </div>
            )}

            <h2>Veřejné hry</h2>

            {publicGames.length === 0 ? (
                <p>
                    Momentálně nejsou žádné hry,
                    ke kterým se můžeš připojit.
                </p>
            ) : (
                <div>
                    {publicGames.map((game) => (
                        <div key={game.id}>
                            <h3>{game.name}</h3>

                            <p>
                                Zakladatel: {game.creator}
                            </p>

                            <GameSettingsSummary game={game} />

                            <button
                                onClick={() =>
                                    handleJoinGame(game.id)
                                }
                            >
                                Připojit se
                            </button>

                            <hr />
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}

export default Home;
