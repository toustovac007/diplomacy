import { useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import Login from "./pages/login";
import Register from "./pages/register";
import Home from "./pages/home";
import GameDetail from "./pages/gameDetail";
import OAuthCallback from "./pages/OAuthCallback";
import VerifyEmail from "./pages/VerifyEmail";
import Ranking from "./pages/Ranking";

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
            <Route path="/ranking" element={<Ranking />} />
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
        <Route path="/verify-email" element={<VerifyEmail />} />
        <Route path="/oauth/callback" element={<OAuthCallback />} />
        <Route path="*" element={<AuthenticatedApp />} />
    </Routes>;
}
