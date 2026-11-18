export default function formatDuration(minutes) {
    if (!Number.isFinite(minutes) || minutes <= 0) return "—";
    if (minutes % 60 !== 0) return `${minutes} min`;
    const hours = minutes / 60;
    return `${hours} ${hours === 1 ? "hodina" : hours >= 2 && hours <= 4 ? "hodiny" : "hodin"}`;
}
