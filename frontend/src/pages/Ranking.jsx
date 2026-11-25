import { useEffect, useState } from "react";
import { useAuth } from "../context/AuthContext";
import api from "../services/api";
import useTokenWallet from "../hooks/useTokenWallet";
import DashboardShell from "../components/DashboardShell";
import { TokenRefillNotice } from "../components/tokens/WalletBalance";

export default function Ranking() {
    const { user, logout } = useAuth();
    const { wallet, walletError, refreshWallet } = useTokenWallet();
    const [leaders, setLeaders] = useState(null);
    const [error, setError] = useState("");
    useEffect(() => {
        let active = true;
        const load = async () => {
            try {
                const { data } = await api.get("users/ranking/");
                if (active) { setLeaders(data); setError(""); }
            } catch {
                if (active) setError("Žebříček se nepodařilo načíst. Další pokus proběhne za minutu.");
            }
        };
        load();
        const timer = window.setInterval(() => { if (document.visibilityState === "visible") load(); }, 60_000);
        return () => { active = false; window.clearInterval(timer); };
    }, []);
    return <DashboardShell username={user?.username} onLogout={logout} headquarters wallet={wallet} walletError={walletError}>
        <main className="home-page ranking-page">
            <header className="home-header"><p className="dashboard-eyebrow">VELITELSTVÍ</p><h1>Žebříček hráčů</h1>
                <p>Top 10 podle součtu dostupných a zmražených tokenů. Při shodě rozhoduje dříve založený účet.</p></header>
            <div className="home-feedback">
                {error && <p role="alert">{error}</p>}
                {walletError && <p role="alert">{walletError} <button type="button" onClick={refreshWallet}>Zkusit znovu</button></p>}
            </div>
            <TokenRefillNotice wallet={wallet} />
            {leaders === null ? <p role="status">Načítám žebříček…</p>
                : <div className="ranking-scroll"><table className="token-ranking">
                    <caption>Nejúspěšnější hráči Diplomacie</caption>
                    <thead><tr><th scope="col">Pořadí</th><th scope="col">Hráč</th><th scope="col">Dostupné</th>
                        <th scope="col">Zmražené</th><th scope="col">Celkem</th></tr></thead>
                    <tbody>{leaders.map((leader) => <tr key={leader.username} className={leader.username === user?.username ? "ranking-current" : ""}>
                        <td>{leader.rank}.</td><th scope="row">{leader.username}{leader.username === user?.username && " (Ty)"}</th>
                        <td>{leader.available.toLocaleString("cs-CZ")}</td><td>{leader.frozen.toLocaleString("cs-CZ")}</td>
                        <td><strong>{leader.total.toLocaleString("cs-CZ")}</strong></td>
                    </tr>)}</tbody>
                </table>{!leaders.length && <p>Zatím tu nejsou žádní ověření hráči.</p>}</div>}
        </main>
    </DashboardShell>;
}
