import { Link } from "react-router-dom";
import GameSettingsSummary from "./GameSettingsSummary";

export default function HomeGameCard({ game, variant, currentUsername, onJoin }) {
    const player = game.players.find((item) => item.username === currentUsername);
    const phase = game.current_phase;
    const finished = variant === "finished";
    const waiting = variant === "waiting" || variant === "join";
    const label = finished ? (game.result_type === "draw" ? "✓ Dokončena — dohoda" : "✓ Dokončena")
        : waiting ? "Čeká na spuštění" : "Aktivní";
    return <article className={`home-game-card home-game-card--${variant}`}>
        <div className="home-game-card__header">
            <span className="home-game-status">{label}</span>
            <h3>{game.name}</h3>
        </div>
        {!waiting && player?.country && <p>Tvůj stát: <strong>{player.country_name || player.country}</strong></p>}
        {variant === "active" && <div className="home-game-card__meta">
            {phase && <>
                <p><strong>{phase.season_name} {phase.year}</strong> — {phase.phase_type_name}</p>
                {phase.deadline && <p>Deadline: <time dateTime={phase.deadline}>{new Date(phase.deadline).toLocaleString("cs-CZ")}</time></p>}
            </>}
            <p>Hráči: {game.players.length} / {game.max_players}</p>
        </div>}
        {waiting && <><p>Zakladatel: {game.creator}</p><GameSettingsSummary game={game} /></>}
        {finished && <>
            {game.result_type === "draw"
                ? <p>Sdílené vítězství: {(game.draw_participants ?? []).map((item) => item.country_name || item.country).join(", ")}</p>
                : game.winner && <p>Vítěz: <strong>{game.winner.country_name || game.winner.country}</strong> — {game.winner.username}</p>}
            {game.finished_at && <p>Dokončeno: <time dateTime={game.finished_at}>{new Date(game.finished_at).toLocaleDateString("cs-CZ")}</time></p>}
        </>}
        <div className="home-game-card__action">
            {variant === "join" ? <button type="button" onClick={() => onJoin(game.id)}>Připojit se</button>
                : <Link to={`/games/${game.id}`}>{finished ? "Zobrazit výsledek" : waiting ? "Otevřít lobby" : "Pokračovat ve hře"}</Link>}
        </div>
    </article>;
}
