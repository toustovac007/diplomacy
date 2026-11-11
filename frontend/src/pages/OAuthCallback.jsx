import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { oauthErrors, providerNames } from "../services/oauth";

export default function OAuthCallback() {
    const { completeOAuthLogin, loading } = useAuth();
    const navigate = useNavigate();
    const [params] = useState(() => new URLSearchParams(window.location.search));
    const [error, setError] = useState("");
    const flight = useRef(null);
    const cleanedUrl = useRef(false);
    useEffect(() => {
        // Remove even failed tickets from history before starting any network work.
        if (!cleanedUrl.current) {
            window.history.replaceState(window.history.state, "", "/oauth/callback");
            cleanedUrl.current = true;
        }
        if (loading) return;
        let active = true;
        if (!flight.current) {
            const ticket = params.get("ticket");
            flight.current = params.get("error") ? Promise.reject(params.get("error"))
                : ticket ? completeOAuthLogin(ticket)
                    : Object.hasOwn(providerNames, params.get("linked")) ? Promise.resolve()
                        : Promise.reject("oauth_failed");
        }
        // Reattach on StrictMode's second effect; exchange itself runs only once.
        flight.current.then(() => { if (active) navigate("/", { replace: true }); })
            .catch((code) => { if (active) setError(Object.hasOwn(oauthErrors, code) ? oauthErrors[code] : oauthErrors.oauth_failed); });
        return () => { active = false; };
    }, [completeOAuthLogin, loading, navigate, params]);
    return <main>
        {error ? <><p role="alert">{error}</p><button onClick={() => navigate("/", { replace: true })}>Zpět na přihlášení</button></>
            : <p>Dokončuji přihlášení...</p>}
    </main>;
}
