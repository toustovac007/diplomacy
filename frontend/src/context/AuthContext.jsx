import { createContext, useContext, useEffect, useState } from "react";
import api, { clearSession, getSessionVersion, startSession, revokeSession } from "../services/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const loadUser = async () => {
            const token = sessionStorage.getItem("access_token");
            const version = getSessionVersion();

            if (!token) {
                setLoading(false);
                return;
            }

            try {
                const response = await api.get("users/me/");
                if (getSessionVersion() === version) {
                    setUser(response.data);
                }
            } catch (error) {
                console.error("User lookup failed", error.response?.status);

                if (getSessionVersion() === version) {
                    clearSession();
                    setUser(null);
                }
            } finally {
                setLoading(false);
            }
        };

        const onCleared = () => setUser(null);
        window.addEventListener("auth-cleared", onCleared);
        loadUser();
        return () => window.removeEventListener("auth-cleared", onCleared);
    }, []);

    const login = async (username, password) => {
        const response = await api.post("token/", {
            username,
            password,
        });

        return finishLogin(response.data);
    };

    const completeOAuthLogin = async (ticket) => {
        const response = await api.post("users/oauth/exchange/", { ticket }, { withCredentials: true });
        return finishLogin(response.data);
    };

    const finishLogin = async ({ access, refresh }) => {
        setUser(null);
        startSession({ access, refresh });
        const version = getSessionVersion();

        try {
            const userResponse = await api.get("users/me/");
            if (getSessionVersion() === version) {
                setUser(userResponse.data);
            }
            return userResponse.data;
        } catch (error) {
            if (getSessionVersion() === version) {
                clearSession();
                setUser(null);
            }
            throw error;
        }
    };

    const register = async (username, email, password) => {
        await api.post("users/register/", {
            username,
            email,
            password,
        });

        // Po registraci uživatele rovnou přihlásíme
        return await login(username, password);
    };

    const logout = async () => {
        setUser(null);
        await revokeSession();
    };

    return (
        <AuthContext.Provider
            value={{ user, login, completeOAuthLogin, register, logout, loading }}
        >
            {children}
        </AuthContext.Provider>
    );
}

export function useAuth() {
    return useContext(AuthContext);
}
