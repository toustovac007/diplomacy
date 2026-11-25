import coin from "../../assets/token-coin.png";
import { refillWait } from "./tokenRules";

export function WalletBalance({ wallet, error }) {
    return <div className="token-wallet" aria-label="Tokenový účet" title={error || "Dostupné a zmražené tokeny"}>
        <span className="token-amount" aria-label={`Dostupné tokeny: ${wallet?.available ?? "načítání"}`}>
            <img src={coin} alt="" /><strong>{error ? "—" : wallet?.available?.toLocaleString("cs-CZ") ?? "…"}</strong>
            <span>Dostupné</span>
        </span>
        <span className="token-amount token-amount--frozen" aria-label={`Zmražené tokeny: ${wallet?.frozen ?? "načítání"}`}>
            <img src={coin} alt="" /><strong>{error ? "—" : wallet?.frozen?.toLocaleString("cs-CZ") ?? "…"}</strong>
            <span>Zmražené</span>
        </span>
    </div>;
}

export function TokenRefillNotice({ wallet }) {
    if (!wallet || wallet.total >= wallet.minimum) return null;
    const wait = wallet.refill_due_at ? refillWait(wallet.refill_due_at) : null;
    return <aside className="token-refill" aria-label="Doplnění tokenů" role="status">
        <strong>Doplnění na {wallet.minimum} tokenů</strong>
        <p>{wait ? wait.ready ? "Čeká na nejbližší hodinovou kontrolu."
            : `Za ${wait.days} d ${wait.hours} h; poté proběhne hodinová kontrola.`
            : "Doplnění se vyhodnotí po dokončení hry."}</p>
        <small>Počítají se dostupné i zmražené tokeny. Doplnění lze získat jednou za 48 hodin.</small>
    </aside>;
}
