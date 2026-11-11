import api from "./api";

export const providerNames = { google: "Google", github: "GitHub" };
export const oauthErrors = {
    access_denied: "Přihlášení bylo zrušeno.",
    account_link_required: "Účet s tímto e-mailem už existuje. Přihlas se heslem a potom Google/GitHub propoj se svým účtem.",
    verified_email_required: "Poskytovatel neposkytl ověřený e-mail.",
    identity_in_use: "Tento externí účet je už propojen s jiným uživatelem.",
    oauth_state_invalid: "Přihlášení není platné. Zkus to znovu.",
    oauth_expired: "Platnost přihlášení vypršela. Zkus to znovu.",
    provider_not_configured: "Tento poskytovatel přihlášení není dostupný.",
    oauth_failed: "Přihlášení se nezdařilo. Zkus to znovu.",
};

export async function startOAuth(provider, link = false) {
    const { data } = await api.post(`users/oauth/${provider}/${link ? "link/" : ""}start/`, {}, { withCredentials: true });
    window.location.assign(data.authorization_url);
}
