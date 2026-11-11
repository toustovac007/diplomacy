import { useState } from "react";
import api from "../services/api";
import { providerNames, startOAuth, oauthErrors } from "../services/oauth";

export default function AccountLogin() {
    const [providers, setProviders] = useState({});
    const [identities, setIdentities] = useState(null);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    async function load(event) {
        if (!event.currentTarget.open) return;
        try {
            const [available, linked] = await Promise.all([api.get("users/oauth/providers/"), api.get("users/oauth/identities/")]);
            setProviders(available.data);
            setIdentities(linked.data);
            setError("");
        } catch { setError("Nepodařilo se načíst propojení účtu."); }
    }
    async function link(provider) {
        setBusy(true);
        setError("");
        try { await startOAuth(provider, true); }
        catch { setError(oauthErrors.oauth_failed); setBusy(false); }
    }
    return <details className="account-login" onToggle={load}>
        <summary>Účet a přihlášení</summary>
        {identities && Object.entries(providerNames).map(([provider, name]) => <p key={provider}>
            {name}: {identities[provider] ? "propojeno" : "nepropojeno"}{" "}
            {providers[provider] && !identities[provider] && <button disabled={busy} onClick={() => link(provider)}>Propojit {name}</button>}
        </p>)}
        {error && <p role="alert">{error}</p>}
    </details>;
}
