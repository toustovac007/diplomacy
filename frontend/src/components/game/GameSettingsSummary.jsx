export default function GameSettingsSummary({ game }) {
    const duration = (minutes) => minutes % 60 === 0 ? `${minutes / 60} h` : `${minutes} min`;
    return <div>
        <p>Hráči: {game.players.length}/{game.max_players} · Viditelnost: {game.is_public ? "Veřejná" : "Soukromá"}</p>
        <p>Pohyby: {duration(game.movement_duration_minutes)} · Ústupy: {duration(game.retreat_duration_minutes)} · Úpravy: {duration(game.adjustment_duration_minutes)}</p>
    </div>;
}
