export const TOKEN_STAKES = [100, 200, 300, 500, 800, 1000, 1500];
export const SCORING_LABELS = { dss: "DSS", sos: "SoS", unranked: "Unranked" };

export function refillWait(dueAt, now = Date.now()) {
    const hours = Math.max(0, Math.ceil((Date.parse(dueAt) - now) / 3_600_000));
    return { days: Math.floor(hours / 24), hours: hours % 24, ready: hours === 0 };
}
