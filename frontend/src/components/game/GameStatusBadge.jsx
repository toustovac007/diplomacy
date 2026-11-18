const statuses = {
    waiting: { emoji: "⏳", label: "Čeká", tone: "waiting" },
    active: { emoji: "⚔️", label: "Probíhá", tone: "active" },
    finished: { emoji: "✅", label: "Dokončeno", tone: "finished" },
};
export default function GameStatusBadge({ status }) {
    const badge = Object.hasOwn(statuses, status) ? statuses[status]
        : { emoji: "❔", label: "Neznámý stav", tone: "unknown" };
    return <span className={`game-status-badge game-status-badge--${badge.tone}`}>
        <span aria-hidden="true">{badge.emoji}</span> {badge.label}
    </span>;
}
