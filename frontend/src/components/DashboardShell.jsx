import mark from "../assets/auth/diplomacie-mark.png";
import "./dashboard.css";

export default function DashboardShell({ username, onLogout, children }) {
    return <div className="dashboard-shell">
        <header className="dashboard-navbar">
            <div className="dashboard-navbar__inner">
                <div className="dashboard-brand"><img src={mark} alt="" /> <span>Diplomacie</span></div>
                <div className="dashboard-user"><span>{username}</span><button type="button" onClick={onLogout}>Odhlásit se</button></div>
            </div>
        </header>
        {children}
    </div>;
}
