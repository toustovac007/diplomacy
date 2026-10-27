import { useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import Login from "./pages/Login";
import Register from "./pages/Register";
import Home from "./pages/Home";
import GameDetail from "./pages/GameDetail";
import OAuthCallback from "./pages/OAuthCallback";

import { useAuth } from "./context/AuthContext";


function AuthenticatedApp() {
    const { user, loading } = useAuth();

    const [showRegister, setShowRegister] = useState(false);


    if (loading) {
        return <p>Načítání...</p>;
    }


    if (!user) {
        if (showRegister) {
            return (
                <Register
                    onBackToLogin={() =>
                        setShowRegister(false)
                    }
                />
            );
        }

        return (
            <Login
                onRegisterClick={() =>
                    setShowRegister(true)
                }
            />
        );
    }


    return (
        <Routes>
            <Route
                path="/"
                element={<Home />}
            />

            <Route
                path="/games/:gameId"
                element={<GameDetail />}
            />

            <Route
                path="*"
                element={
                    <Navigate
                        to="/"
                        replace
                    />
                }
            />
        </Routes>
    );
}


export default function App() {
    return <Routes>
        <Route path="/oauth/callback" element={<OAuthCallback />} />
        <Route path="*" element={<AuthenticatedApp />} />
    </Routes>;
}
