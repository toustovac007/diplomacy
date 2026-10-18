import { useEffect, useState } from "react";
import { useAuth } from "../context/AuthContext";
import api from "../services/api";
import { Link } from "react-router-dom";


function Home() {
    const { user, logout } = useAuth();

    const [games, setGames] = useState([]);
    const [publicGames, setPublicGames] = useState([]);

    const [name, setName] = useState("");
    const [turnDuration, setTurnDuration] = useState(1440);

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
                turn_duration_minutes: Number(turnDuration),
                max_players: 7,
            });

            setName("");

            setMessage("Hra byla vytvořena.");

            await loadAllGames();

        } catch (error) {
            console.error(error);
            setError("Hru se nepodařilo vytvořit.");
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
                    <label>Délka kola</label>
                    <br />

                    <select
                        value={turnDuration}
                        onChange={(event) =>
                            setTurnDuration(event.target.value)
                        }
                    >
                        <option value={60}>
                            1 hodina
                        </option>

                        <option value={360}>
                            6 hodin
                        </option>

                        <option value={720}>
                            12 hodin
                        </option>

                        <option value={1440}>
                            24 hodin
                        </option>

                        <option value={2880}>
                            48 hodin
                        </option>

                        <option value={4320}>
                            72 hodin
                        </option>
                    </select>
                </div>

                <br />

                <button type="submit">
                    Vytvořit hru
                </button>
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

                            <p>
                                Stav: {game.status === "finished"
                                    ? `Dokončena${game.winner ? ` — vítěz: ${game.winner.country_name}` : ""}`
                                    : game.status}
                            </p>

                            <p>
                                Hráči:{" "}
                                {game.players.length}/
                                {game.max_players}
                            </p>

                            <p>
                                Délka kola:{" "}
                                {game.turn_duration_minutes} minut
                            </p>

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

                            <p>
                                Hráči:{" "}
                                {game.players.length}/
                                {game.max_players}
                            </p>

                            <p>
                                Délka kola:{" "}
                                {game.turn_duration_minutes} minut
                            </p>

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
