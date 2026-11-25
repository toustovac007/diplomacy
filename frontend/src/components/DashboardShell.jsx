import mark from "../assets/auth/diplomacie-mark.png";
import "./dashboard.css";
import { NavLink } from "react-router-dom";
import { WalletBalance } from "./tokens/WalletBalance";

export default function DashboardShell({ username, onLogout, headquarters = false, wallet, walletError, children }) {
    return <div className="dashboard-shell">
        <header className="dashboard-navbar">
            <div className="dashboard-navbar__inner">
                <div className="dashboard-brand"><img src={mark} alt="" /> <span>Diplomacie</span></div>
                {headquarters && <nav className="dashboard-navigation" aria-label="Velitelství">
                    <NavLink to="/" end>Moje hry</NavLink><NavLink to="/ranking">Žebříček</NavLink>
                </nav>}
                <div className="dashboard-user">
                    {headquarters && <WalletBalance wallet={wallet} error={walletError} />}
                    <span>{username}</span><button type="button" onClick={onLogout}>Odhlásit se</button>
                </div>
            </div>
        </header>
        {children}
    </div>;
}
