import { createContext, useContext, useEffect, useState } from "react";
import api from "../services/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const loadUser = async () => {
            const token = localStorage.getItem("access_token");

            if (!token) {
                setLoading(false);
                return;
            }

            try {
                const response = await api.get("users/me/");
                setUser(response.data);
            } catch (error) {
                console.error("Nepodařilo se načíst uživatele:", error);

                localStorage.removeItem("access_token");
                localStorage.removeItem("refresh_token");
                setUser(null);
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

        localStorage.setItem("access_token", access);
        localStorage.setItem("refresh_token", refresh);

        const userResponse = await api.get("users/me/");
        setUser(userResponse.data);

        return userResponse.data;
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
        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token");

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