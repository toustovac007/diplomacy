import { useState } from "react";
import { Link } from "react-router-dom";
import DashboardShell from "../DashboardShell";
import GameStatusBadge from "./GameStatusBadge";
import formatDuration from "./formatDuration";
import "./waitingLobby.css";

export default function WaitingLobby({ game, username, onLogout, onStart, starting, error, message, refreshError }) {
    const [copyMessage, setCopyMessage] = useState("");
    const copyCode = async () => {
        try {
            await navigator.clipboard.writeText(game.invite_code);
            setCopyMessage("Kód zkopírován.");
        } catch {
            setCopyMessage("Kód se nepodařilo zkopírovat. Označ ho a zkopíruj ručně.");
        }
    };
    const settings = [
        ["Zakladatel", game.creator],
        ["Viditelnost", game.is_public ? "Veřejná" : "Soukromá"],
        ["Maximální počet hráčů", game.max_players],
        ["Pohyby", formatDuration(game.movement_duration_minutes)],
        ["Ústupy", formatDuration(game.retreat_duration_minutes)],
        ["Zimní úpravy", formatDuration(game.adjustment_duration_minutes)],
    ];
    return <DashboardShell username={username} onLogout={onLogout}>
        <main className="waiting-lobby">
            <header className="waiting-lobby__header">
                <Link to="/">← Zpět na moje hry</Link>
                <p className="waiting-lobby__eyebrow">Lobby</p>
                <h1>{game.name}</h1>
                <div className="waiting-lobby__summary"><GameStatusBadge status={game.status} />
                    <span>Hráči {game.players.length} / {game.max_players}</span></div>
                {refreshError && <p role="status">{refreshError}</p>}
            </header>
            <div className="waiting-lobby__grid">
                <section className="waiting-lobby__card" aria-labelledby="lobby-players-title">
                    <h2 id="lobby-players-title">Hráči</h2>
                    <ul className="waiting-lobby__players">
                        {game.players.map((player) => <li key={player.id}>
                            <strong>{player.username}</strong>
                            <div className="waiting-lobby__player-labels">
                                {player.username === game.creator && <span>Zakladatel</span>}
                                {player.username === username && <span>Ty</span>}
                                {player.country_name && <span>{player.country_name}</span>}
                            </div>
                        </li>)}
                    </ul>
                    <div className="waiting-lobby__start">
                        {game.creator === username ? <>
                            <p>Jsi zakladatel této hry.</p>
                            <button type="button" onClick={onStart} disabled={starting || game.players.length < 2}>
                                {starting ? "Spouštím…" : "Spustit hru"}
                            </button>
                            {game.players.length < 2 && <p>Pro spuštění jsou potřeba alespoň 2 hráči.</p>}
                        </> : <p>Čeká se, až zakladatel spustí hru.</p>}
                        {error && <p role="alert">{error}</p>}
                        {message && <p role="status">{message}</p>}
                    </div>
                </section>
                <div className="waiting-lobby__side">
                    {game.invite_code && <section className="waiting-lobby__card game-lobby-invitation" aria-labelledby="lobby-invitation-title">
                        <h2 id="lobby-invitation-title">Pozvánka</h2>
                        <p>Sdílej tento kód s hráči, které chceš pozvat do hry.</p>
                        <code className="game-invite-code">{game.invite_code}</code>
                        <button type="button" onClick={copyCode}>Zkopírovat kód</button>
                        <p role="status" aria-live="polite">{copyMessage}</p>
                    </section>}
                    <section className="waiting-lobby__card" aria-labelledby="lobby-settings-title">
                        <h2 id="lobby-settings-title">Nastavení hry</h2>
                        <dl className="waiting-lobby__settings">
                            {settings.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}
                        </dl>
                    </section>
                </div>
            </div>
        </main>
    </DashboardShell>;
}
