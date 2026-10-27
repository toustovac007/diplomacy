import { useEffect, useRef, useState } from "react";
import { useAuth } from "../context/AuthContext";
import api from "../services/api";
import HomeGameCard from "../components/game/HomeGameCard";
import NotificationSettings from "../components/NotificationSettings";
import AccountLogin from "../components/AccountLogin";

const defaultSettings = {
    max_players: 7,
    is_public: true,
    movement_duration_minutes: 1440,
    retreat_duration_minutes: 720,
    adjustment_duration_minutes: 720,
};
const durationFields = [
    ["movement_duration_minutes", "Pohyby", [60, 360, 720, 1440, 2880, 4320]],
    ["retreat_duration_minutes", "Ústupy", [60, 360, 720, 1440]],
    ["adjustment_duration_minutes", "Zimní úpravy", [60, 360, 720, 1440]],
];
const fieldLabels = Object.fromEntries([
    ["name", "Název hry"], ["max_players", "Počet hráčů"], ["is_public", "Viditelnost"],
    ["invite_code", "Pozvánka"], ...durationFields.map(([field, label]) => [field, label]),
]);
function backendError(error, fallback) {
    const data = error.response?.data;
    if (!data || typeof data !== "object") return fallback;
    if (data.detail) return data.detail;
    return Object.entries(data).map(([field, messages]) =>
        `${fieldLabels[field] || field}: ${Array.isArray(messages) ? messages.join(" ") : messages}`
    ).join(" ") || fallback;
}


function Home() {
    const { user, logout } = useAuth();

    const [games, setGames] = useState([]);
    const [publicGames, setPublicGames] = useState([]);
    const [selectedTab, setSelectedTab] = useState(null);
    const [loaded, setLoaded] = useState(false);
    const createPanel = useRef(null);
    const invitePanel = useRef(null);
    const activeGames = games.filter((game) => game.status === "active");
    const waitingGames = games.filter((game) => game.status === "waiting");
    const finishedGames = games.filter((game) => game.status === "finished")
        .sort((a, b) => (Date.parse(b.finished_at) || 0) - (Date.parse(a.finished_at) || 0));
    const tabs = [
        { id: "active", label: "Aktivní", games: activeGames, empty: "Momentálně nemáš žádnou rozehranou hru." },
        { id: "waiting", label: "Čekající", games: waitingGames, empty: "Nemáš žádnou hru čekající na spuštění." },
        { id: "join", label: "Připojit se", games: publicGames, empty: "Momentálně nejsou žádné veřejné hry, ke kterým se můžeš připojit." },
        { id: "finished", label: "Dokončené", games: finishedGames, empty: "Zatím nemáš žádnou dokončenou hru." },
    ];

    const [name, setName] = useState("");
    const [settings, setSettings] = useState(defaultSettings);
    const [inviteCode, setInviteCode] = useState("");

    const [error, setError] = useState("");
    const [message, setMessage] = useState("");


    const loadGames = async () => {
        try {
            const response = await api.get("games/");
            setGames(response.data);
            return response.data;
        } catch (error) {
            console.error("API request failed", error.response?.status);
            setError("Nepodařilo se načíst tvoje hry.");
        }
    };


    const loadPublicGames = async () => {
        try {
            const response = await api.get("games/public/");
            setPublicGames(response.data);
            return response.data;
        } catch (error) {
            console.error("API request failed", error.response?.status);
            setError("Nepodařilo se načíst veřejné hry.");
        }
    };


    const loadAllGames = async () => {
        const [own = [], joinable = []] = await Promise.all([loadGames(), loadPublicGames()]);
        setSelectedTab((current) => current ?? (own.some((game) => game.status === "active") ? "active"
            : own.some((game) => game.status === "waiting") ? "waiting" : joinable.length ? "join" : "finished"));
        setLoaded(true);
    };


    useEffect(() => {
        loadAllGames();
    }, []);


    const handleCreateGame = async (event) => {
        event.preventDefault();
        createPanel.current.open = true;

        setError("");
        setMessage("");

        if (!name.trim()) {
            setError("Zadej název hry.");
            return;
        }

        try {
            await api.post("games/", {
                name: name,
                ...settings,
            });

            setName("");
            setSettings(defaultSettings);

            setMessage("Hra byla vytvořena.");

            await loadAllGames();

        } catch (error) {
            console.error("API request failed", error.response?.status);
            createPanel.current.open = true;
            setError(backendError(error, "Hru se nepodařilo vytvořit."));
        }
    };


    const handleJoinGame = async (gameId) => {
        setError("");
        setMessage("");

        try {
            await api.post(`games/${gameId}/join/`);

            setMessage("Úspěšně ses připojil ke hře.");

            await loadAllGames();

        } catch (error) {
            console.error("API request failed", error.response?.status);

            const backendMessage =
                error.response?.data?.detail;

            if (backendMessage) {
                setError(backendMessage);
            } else {
                setError("Ke hře se nepodařilo připojit.");
            }
        }
    };


    const handleJoinByCode = async (event) => {
        event.preventDefault();
        invitePanel.current.open = true;
        setError("");
        setMessage("");
        try {
            await api.post("games/join-by-code/", { invite_code: inviteCode.trim() });
            setInviteCode("");
            setMessage("Úspěšně ses připojil ke hře.");
            await loadAllGames();
        } catch (error) {
            setError(backendError(error, "Ke hře se nepodařilo připojit."));
        }
    };

    return (
        <main className="home-page">
            <header className="home-header">
                <div><h1>Diplomacy</h1><p>Přihlášen jako: <strong>{user?.username}</strong></p></div>
                <button type="button" onClick={logout}>Odhlásit se</button>
            </header>
            <div className="home-actions">
                <details className="home-action-panel" ref={createPanel}>
                    <summary>+ Vytvořit novou hru</summary>
            <form onSubmit={handleCreateGame}>
                <div>
                    <label htmlFor="game-name">Název hry</label>
                    <br />

                    <input
                        id="game-name"
                        type="text"
                        value={name}
                        onChange={(event) =>
                            setName(event.target.value)
                        }
                    />
                </div>

                <div>
                    <label htmlFor="max-players">Počet hráčů</label>{" "}
                    <select id="max-players" value={settings.max_players}
                        onChange={(event) => setSettings({ ...settings, max_players: Number(event.target.value) })}>
                        {[2, 3, 4, 5, 6, 7].map((count) => <option key={count} value={count}>{count}</option>)}
                    </select>
                </div>
                <div>
                    <label htmlFor="visibility">Viditelnost</label>{" "}
                    <select id="visibility" value={String(settings.is_public)}
                        onChange={(event) => setSettings({ ...settings, is_public: event.target.value === "true" })}>
                        <option value="true">Veřejná</option>
                        <option value="false">Soukromá</option>
                    </select>
                </div>
                {durationFields.map(([field, label, values]) => <div key={field}>
                    <label htmlFor={field}>{label}</label>{" "}
                    <select id={field} value={settings[field]}
                        onChange={(event) => setSettings({ ...settings, [field]: Number(event.target.value) })}>
                        {values.map((minutes) => <option key={minutes} value={minutes}>{minutes / 60} h</option>)}
                    </select>
                </div>)}

                <br />

                <button type="submit">
                    Vytvořit hru
                </button>
            </form>

                </details>
                <details className="home-action-panel" ref={invitePanel}>
                    <summary>Připojit se pomocí pozvánky</summary>
            <form onSubmit={handleJoinByCode}>
                <label htmlFor="invite-code">Kód pozvánky</label>{" "}
                <input id="invite-code" value={inviteCode} required
                    onChange={(event) => setInviteCode(event.target.value)} />{" "}
                <button type="submit">Připojit se</button>
            </form>

                </details>
                <details className="home-action-panel">
                    <summary>E-mailová upozornění</summary>
                    <NotificationSettings key={user?.username} />
                    <AccountLogin key={`account-${user?.username}`} />
                </details>
            </div>
            <div className="home-feedback">
                {error && <p role="alert">{error}</p>}
                {message && <p role="status">{message}</p>}
            </div>
            {!loaded ? <p role="status">Načítám hry…</p> : <>
                <div className="game-tabs home-tabs" role="tablist" aria-label="Přehled her">
                    {tabs.map((tab, index) => <button key={tab.id} type="button" role="tab" className="game-tab"
                        id={`home-tab-${tab.id}`} aria-selected={selectedTab === tab.id} aria-controls={`home-panel-${tab.id}`}
                        tabIndex={selectedTab === tab.id ? 0 : -1} onClick={() => setSelectedTab(tab.id)}
                        onKeyDown={(event) => {
                            const next = event.key === "ArrowRight" ? (index + 1) % tabs.length
                                : event.key === "ArrowLeft" ? (index + tabs.length - 1) % tabs.length
                                : event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : null;
                            if (next === null) return;
                            event.preventDefault();
                            setSelectedTab(tabs[next].id);
                            document.getElementById(`home-tab-${tabs[next].id}`).focus();
                        }}>{tab.label} ({tab.games.length})</button>)}
                </div>
                {tabs.map((tab) => <section key={tab.id} className="game-tab-panel home-tab-panel" role="tabpanel"
                    id={`home-panel-${tab.id}`} aria-labelledby={`home-tab-${tab.id}`} hidden={selectedTab !== tab.id} tabIndex={0}>
                    {tab.games.length ? <div className="game-card-grid">
                        {tab.games.map((game) => <HomeGameCard key={game.id} game={game} variant={tab.id}
                            currentUsername={user?.username} onJoin={handleJoinGame} />)}
                    </div> : <p className="home-empty-state">{tab.empty}</p>}
                </section>)}
            </>}
        </main>
    );
}

export default Home;
