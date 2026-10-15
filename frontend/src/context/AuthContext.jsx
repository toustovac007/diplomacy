import { createContext, useContext, useEffect, useState } from "react";
import api from "../services/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const loadUser = async () => {
            const token = sessionStorage.getItem("access_token");
            const refreshToken = sessionStorage.getItem("refresh_token");

            if (!token) {
                setLoading(false);
                return;
            }

            try {
                const response = await api.get("users/me/");
                if (sessionStorage.getItem("refresh_token") === refreshToken) {
                    setUser(response.data);
                }
            } catch (error) {
                console.error("Nepodařilo se načíst uživatele:", error);

                if (sessionStorage.getItem("refresh_token") === refreshToken) {
                    sessionStorage.removeItem("access_token");
                    sessionStorage.removeItem("refresh_token");
                    setUser(null);
                }
            } finally {
                setLoading(false);
            }
        };

        loadUser();
    }, []);

    const login = async (username, password) => {
        const response = await api.post("token/", {
            username,
            password,
        });

        const { access, refresh } = response.data;

        setUser(null);
        sessionStorage.setItem("access_token", access);
        sessionStorage.setItem("refresh_token", refresh);

        try {
            const userResponse = await api.get("users/me/");
            if (sessionStorage.getItem("refresh_token") === refresh) {
                setUser(userResponse.data);
            }
            return userResponse.data;
        } catch (error) {
            if (sessionStorage.getItem("refresh_token") === refresh) {
                sessionStorage.removeItem("access_token");
                sessionStorage.removeItem("refresh_token");
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

    const logout = () => {
        sessionStorage.removeItem("access_token");
        sessionStorage.removeItem("refresh_token");

        setUser(null);
    };

    return (
        <AuthContext.Provider
            value={{ user, login, register, logout, loading }}
        >
            {children}
        </AuthContext.Provider>
    );
}

export function useAuth() {
    return useContext(AuthContext);
}
