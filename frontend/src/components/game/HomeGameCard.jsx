import { Link } from "react-router-dom";
import GameStatusBadge from "./GameStatusBadge";
import formatDuration from "./formatDuration";
import { SCORING_LABELS } from "../tokens/tokenRules";

export default function HomeGameCard({ game, variant, currentUsername, availableTokens, onJoin }) {
    const player = (game.players ?? []).find((item) => item.username === currentUsername);
    const phase = game.current_phase;
    const finished = variant === "finished";
    const waiting = variant === "waiting" || variant === "join";
    const affordable = availableTokens != null && availableTokens >= (game.token_stake ?? 100);
    return <article className={`home-game-card home-game-card--${variant}`}>
        <div className="home-game-card__header">
            <h3>{game.name}</h3>
            <GameStatusBadge status={game.status} />
        </div>
        {!waiting && player?.country && <p>Tvůj stát: <strong>{player.country_name || player.country}</strong></p>}
        {variant === "active" && <div className="home-game-card__meta">
            {phase && <>
                <p><strong>{phase.season_name} {phase.year}</strong> — {phase.phase_type_name}</p>
                {phase.deadline && <p>Deadline: <time dateTime={phase.deadline}>{new Date(phase.deadline).toLocaleString("cs-CZ")}</time></p>}
            </>}

        </div>}
        <dl className="dashboard-game-stats">
            {game.token_stake != null && <div><dt>Sázka / bodování</dt><dd>{game.token_stake} · {SCORING_LABELS[game.scoring]}</dd></div>}
            {game.token_pot != null && <div><dt>Bank</dt><dd>{game.token_pot} tokenů</dd></div>}
            {game.players && <div><dt>Hráči</dt><dd>{game.players.length} / {game.max_players}</dd></div>}
            {(game.movement_duration_minutes ?? game.turn_duration_minutes) != null && <div><dt>Pohyby</dt><dd>{formatDuration(game.movement_duration_minutes ?? game.turn_duration_minutes)}</dd></div>}
            {game.retreat_duration_minutes != null && <div><dt>Ústupy</dt><dd>{formatDuration(game.retreat_duration_minutes)}</dd></div>}
            {game.adjustment_duration_minutes != null && <div><dt>Úpravy</dt><dd>{formatDuration(game.adjustment_duration_minutes)}</dd></div>}
        </dl>
        {game.creator && <p>Zakladatel: {game.creator}</p>}
        {waiting && <p>Viditelnost: {game.is_public ? "Veřejná" : "Soukromá"}</p>}
        {waiting && variant !== "join" && !game.is_public && game.invite_code && <p>Pozvánka: <code>{game.invite_code}</code></p>}
        {finished && <>
            {player?.token_payout != null && <p>Tvoje výplata: <strong>{player.token_payout} tokenů</strong></p>}
            {game.result_type === "draw"
                ? <p>Sdílené vítězství: {(game.draw_participants ?? []).map((item) => item.country_name || item.country).join(", ")}</p>
                : game.winner && <p>Vítěz: <strong>{game.winner.country_name || game.winner.country}</strong> — {game.winner.username}</p>}
            {game.finished_at && <p>Dokončeno: <time dateTime={game.finished_at}>{new Date(game.finished_at).toLocaleDateString("cs-CZ")}</time></p>}
        </>}
        <div className="home-game-card__action">
            {variant === "join" ? <button type="button" disabled={!affordable} onClick={() => onJoin(game.id)}
                title={!affordable ? "Nemáš dost dostupných tokenů, nebo se zůstatek ještě načítá." : undefined}>
                {availableTokens != null && !affordable ? "Nedostatek tokenů" : "Připojit se"}</button>
                : <Link to={`/games/${game.id}`}>{finished ? "Zobrazit výsledek" : waiting ? "Otevřít lobby" : "Pokračovat ve hře"}</Link>}
        </div>
    </article>;
}
