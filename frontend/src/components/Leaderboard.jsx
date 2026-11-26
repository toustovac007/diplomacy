import { useEffect, useState } from "react";
import api from "../services/api";

export default function Leaderboard({ username }) {
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
    return <>
        {error && <div className="home-feedback"><p role="alert">{error}</p></div>}
        {leaders === null ? <p role="status">Načítám žebříček…</p>
            : <div className="ranking-scroll"><table className="token-ranking">
                <caption>Nejúspěšnější hráči Diplomacie</caption>
                <thead><tr><th scope="col">Pořadí</th><th scope="col">Hráč</th><th scope="col">Dostupné</th>
                    <th scope="col">Zmražené</th><th scope="col">Celkem</th></tr></thead>
                <tbody>{leaders.map((leader) => <tr key={leader.username} className={leader.username === username ? "ranking-current" : ""}>
                    <td>{leader.rank}.</td><th scope="row">{leader.username}{leader.username === username && " (Ty)"}</th>
                    <td>{leader.available.toLocaleString("cs-CZ")}</td><td>{leader.frozen.toLocaleString("cs-CZ")}</td>
                    <td><strong>{leader.total.toLocaleString("cs-CZ")}</strong></td>
                </tr>)}</tbody>
            </table>{!leaders.length && <p>Zatím tu nejsou žádní ověření hráči.</p>}</div>}
    </>;
}
