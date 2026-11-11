import { useEffect, useState } from "react";
import api from "../services/api";
import { providerNames, startOAuth, oauthErrors } from "../services/oauth";

export default function SocialLogin() {
    const [providers, setProviders] = useState({});
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    useEffect(() => {
        let active = true;
        api.get("users/oauth/providers/").then(({ data }) => { if (active) setProviders(data); }).catch(() => {});
        return () => { active = false; };
    }, []);
    const enabled = Object.keys(providerNames).filter((provider) => providers[provider] === true);
    if (!enabled.length) return null;
    async function start(provider) {
        setBusy(true);
        setError("");
        try { await startOAuth(provider); }
        catch { setError(oauthErrors.oauth_failed); setBusy(false); }
    }
    return <section className="social-login" aria-label="Další možnosti přihlášení">
        <p>nebo</p>
        {enabled.map((provider) => <button key={provider} disabled={busy} onClick={() => start(provider)}>
            Pokračovat přes {providerNames[provider]}
        </button>)}
        {error && <p role="alert">{error}</p>}
    </section>;
}
