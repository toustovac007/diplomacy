import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import api from "../services/api";
import { useAuth } from "../context/AuthContext";


function GameDetail() {
    const { gameId } = useParams();
    const { user } = useAuth();

    const [game, setGame] = useState(null);
    const [loading, setLoading] = useState(true);

    const [error, setError] = useState("");
    const [message, setMessage] = useState("");


    const loadGame = async () => {
        try {
            const response = await api.get(`games/${gameId}/`);

            setGame(response.data);
        } catch (error) {
            console.error(error);

            if (error.response?.status === 404) {
                setError(
                    "Hra neexistuje nebo do ní nemáš přístup."
                );
            } else {
                setError("Nepodařilo se načíst hru.");
            }
        } finally {
            setLoading(false);
        }
    };


    useEffect(() => {
        loadGame();
    }, [gameId]);


    const handleStartGame = async () => {
        setError("");
        setMessage("");

        try {
            const response = await api.post(
                `games/${gameId}/start/`
            );

            setGame(response.data);
            setMessage("Hra byla spuštěna.");

        } catch (error) {
            console.error(error);

            const backendMessage =
                error.response?.data?.detail;

            if (backendMessage) {
                setError(backendMessage);
            } else {
                setError("Hru se nepodařilo spustit.");
            }
        }
    };


    if (loading) {
        return <p>Načítání hry...</p>;
    }


    if (!game) {
        return (
            <div>
                <p>{error}</p>

                <Link to="/">
                    ← Zpět na hlavní stránku
                </Link>
            </div>
        );
    }


    const isCreator =
        game.creator === user?.username;


    return (
        <div>
            <Link to="/">
                ← Zpět na moje hry
            </Link>

            <h1>{game.name}</h1>

            <p>
                Zakladatel:{" "}
                <strong>{game.creator}</strong>
            </p>

            <p>
                Stav:{" "}
                <strong>{game.status}</strong>
            </p>

            <p>
                Délka kola:{" "}
                <strong>
                    {game.turn_duration_minutes} minut
                </strong>
            </p>

            <p>
                Počet hráčů:{" "}
                <strong>
                    {game.players.length}/{game.max_players}
                </strong>
            </p>


            {error && (
                <p>{error}</p>
            )}

            {message && (
                <p>{message}</p>
            )}


            <hr />

            <h2>Hráči</h2>

            <ul>
                {game.players.map((player) => (
                    <li key={player.id}>
                        <strong>{player.username}</strong>

                        {player.username === game.creator &&
                            " (zakladatel)"
                        }

                        {player.country_name && (
                            <>
                                {" — "}
                                {player.country_name}
                            </>
                        )}
                    </li>
                ))}
            </ul>

            {game.status === "waiting" && (
                <>
                    <hr />

                    <h2>Lobby</h2>

                    {isCreator ? (
                        <>
                            <p>
                                Jsi zakladatel této hry.
                            </p>

                            <button
                                onClick={handleStartGame}
                                disabled={
                                    game.players.length < 2
                                }
                            >
                                Spustit hru
                            </button>

                            {game.players.length < 2 && (
                                <p>
                                    Pro spuštění jsou potřeba
                                    alespoň 2 hráči.
                                </p>
                            )}
                        </>
                    ) : (
                        <p>
                            Čeká se, až zakladatel
                            spustí hru.
                        </p>
                    )}
                </>
            )}

            {game.status === "active" && (
                <>
                    <hr />

                    <h2>Hra probíhá</h2>

                    {game.current_phase ? (
                        <div>
                            <h3>
                                {game.current_phase.season_name}{" "}
                                {game.current_phase.year}
                            </h3>

                            <p>
                                Fáze:{" "}
                                <strong>
                                    {game.current_phase.phase_type_name}
                                </strong>
                            </p>

                            <p>
                                Stav:{" "}
                                <strong>
                                    {game.current_phase.status}
                                </strong>
                            </p>

                            <h3>Jednotky</h3>

                            <ul>
                                {game.units.map((unit) => (
                                    <li key={unit.id}>
                                        <strong>
                                            {unit.unit_type === "army" ? "A" : "F"}
                                        </strong>
                                        {" "}
                                        {unit.province_name}
                                        {unit.coast && ` (${unit.coast.toUpperCase()})`}
                                        {" — "}
                                        {unit.country_name}
                                        {" — "}
                                        {unit.owner_username}
                                    </li>
                                ))}
                            </ul>

                            <p>
                                Deadline:{" "}
                                <strong>
                                    {new Date(
                                        game.current_phase.deadline
                                    ).toLocaleString("cs-CZ")}
                                </strong>
                            </p>
                        </div>
                    ) : (
                        <p>
                            Aktivní fáze nebyla nalezena.
                        </p>
                    )}
                </>
            )}
        </div>
    );
}


export default GameDetail;