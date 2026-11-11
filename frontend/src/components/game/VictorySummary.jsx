import { Link } from "react-router-dom";
import { COUNTRY_COLORS } from "./countryColors";

function finalStandings(game) {
    const centers = new Map();
    const units = new Map();
    for (const center of game.supply_centers ?? []) {
        if (center.owner_country) centers.set(center.owner_country, (centers.get(center.owner_country) ?? 0) + 1);
    }
    for (const unit of game.units ?? []) {
        if (unit.country) units.set(unit.country, (units.get(unit.country) ?? 0) + 1);
    }
    return (game.players ?? []).map((player) => ({
        ...player, centers: centers.get(player.country) ?? 0, units: units.get(player.country) ?? 0,
    })).sort((a, b) => b.centers - a.centers || a.id - b.id);
}

export default function VictorySummary({ game }) {
    const standings = finalStandings(game);
    const winner = game.winner;
    const isDraw = game.result_type === "draw";
    const shared = game.draw_participants ?? [];
    const color = COUNTRY_COLORS[winner?.country] ?? "var(--border)";
    return (
        <>
            <header className="victory-card" style={{ "--winner-color": color }}>
                <div className="victory-heading">
                    <p className="victory-eyebrow">Konečný výsledek</p>
                    <h2>{isDraw ? "Hra skončila dohodou" : "Hra skončila"}</h2>
                    <Link className="victory-return" to="/">Zpět na moje hry <span aria-hidden="true">↗</span></Link>
                </div>
                {isDraw ? <div className="victory-result">
                    <div>
                        <h3>Sdílené vítězství</h3>
                        <ul className="draw-result">{shared.map((player) => <li key={player.id}>
                            <span className="country-swatch" style={{ backgroundColor: COUNTRY_COLORS[player.country] }} />
                            {player.country_name || player.country} — {player.username}
                        </li>)}</ul>
                    </div>
                </div> : winner ? <div className="victory-result">
                    <div>
                        <p className="victory-eyebrow">Vítěz</p>
                        <h3 className="victory-country">{winner.country_name ?? winner.country}</h3>
                        <span className="victory-country-code">{winner.country}</span>
                        <p className="victory-player">Hráč: <strong>{winner.username}</strong></p>
                    </div>
                    <div className="victory-score">
                        <strong>{game.winner_supply_center_count ?? standings.find((row) => row.id === winner.id)?.centers ?? "—"}</strong>
                        <span>Supply centra</span>
                    </div>
                </div> : <p className="victory-fallback">Údaj o vítězi není k dispozici.</p>}
                {game.finished_at && <p className="victory-meta">Ukončeno: <time dateTime={game.finished_at}>
                    {new Date(game.finished_at).toLocaleString("cs-CZ")}
                </time></p>}
            </header>

            <section className="final-standings" aria-labelledby="final-standings-title">
                <h3 id="final-standings-title">Konečné pořadí</h3>
                <div className="final-standings-scroll">
                    <table>
                        <caption className="victory-table-caption">Pořadí podle počtu supply center. Při shodě je pořadí pomocné.</caption>
                        <thead><tr><th scope="col">Stát</th><th scope="col">Hráč</th><th scope="col">Supply centra</th><th scope="col">Jednotky</th></tr></thead>
                        <tbody>{standings.map((row) => <tr key={row.id} className={row.id === winner?.id || shared.some((p) => p.id === row.id) ? "final-standings-winner" : undefined}>
                            <th scope="row"><span className="country-swatch" aria-hidden="true" style={{ backgroundColor: COUNTRY_COLORS[row.country] ?? "var(--border)" }} />
                                {row.country_name ?? row.country ?? "Nepřiřazený stát"}
                                {row.id === winner?.id && <span className="victory-winner-label">Vítěz</span>}
                                {isDraw && shared.some((p) => p.id === row.id) && <span className="victory-winner-label">Sdílené vítězství</span>}
                            </th>
                            <td>{row.username}</td><td className="standings-number">{row.centers}</td><td className="standings-number">{row.units}</td>
                        </tr>)}</tbody>
                    </table>
                </div>
            </section>
        </>
    );
}
