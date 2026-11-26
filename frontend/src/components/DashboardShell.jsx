import "./dashboard.css";
import { Link } from "react-router-dom";
import { WalletBalance } from "./tokens/WalletBalance";

const views = [
    ["active", "Aktivní", "/?view=active"],
    ["waiting", "Čekající", "/?view=waiting"],
    ["finished", "Dokončené", "/?view=finished"],
    ["public", "Veřejné hry", "/?view=public"],
    ["ranking", "Žebříček", "/ranking"],
];

export default function DashboardShell({ username, onLogout, headquarters = false, activeView = "active", wallet, walletError, children }) {
    return <div className="dashboard-shell">
        <header className="dashboard-navbar">
            <div className="dashboard-navbar__inner">
                <Link className="dashboard-brand" to="/?view=active" aria-label="Diplomacie – aktivní hry">
                    <img src="/diplomacie-mark.svg" width="40" height="40" alt="" /> <span>Diplomacie</span>
                </Link>
                {headquarters && <nav className="dashboard-navigation" aria-label="Velitelství">
                    {views.map(([id, label, to], index) => <Link key={id} id={`home-nav-${id}`} to={to}
                        className={activeView === id ? "active" : undefined}
                        aria-current={activeView === id ? "page" : undefined}
                        onKeyDown={(event) => {
                            const next = event.key === "ArrowRight" ? (index + 1) % views.length
                                : event.key === "ArrowLeft" ? (index + views.length - 1) % views.length
                                : event.key === "Home" ? 0 : event.key === "End" ? views.length - 1 : null;
                            if (next === null) return;
                            event.preventDefault();
                            const target = event.currentTarget.parentElement.querySelectorAll("a")[next];
                            target.focus();
                            target.click();
                        }}>{label}</Link>)}
                </nav>}
                <div className="dashboard-user">
                    {headquarters && <WalletBalance wallet={wallet} error={walletError} />}
                    <span className="dashboard-username" title={username}>{username}</span><button type="button" onClick={onLogout}>Odhlásit se</button>
                </div>
            </div>
        </header>
        {children}
    </div>;
}
