import { useCallback, useEffect, useRef, useState } from "react";
import api, { getSessionVersion } from "../services/api";

export default function useTokenWallet() {
    const [wallet, setWallet] = useState(null);
    const [walletError, setWalletError] = useState("");
    const mounted = useRef(false);
    const latest = useRef(0);
    const refreshWallet = useCallback(() => {
        const request = ++latest.current;
        const session = getSessionVersion();
        return api.get("users/tokens/").then(({ data }) => {
            if (mounted.current && request === latest.current && session === getSessionVersion()) {
                setWallet(data);
                setWalletError("");
            }
        }, () => {
            if (mounted.current && request === latest.current && session === getSessionVersion()) {
                setWalletError("Zůstatek se nepodařilo aktualizovat.");
            }
        });
    }, []);
    useEffect(() => {
        mounted.current = true;
        refreshWallet();
        const refreshVisible = () => { if (document.visibilityState === "visible") refreshWallet(); };
        const timer = window.setInterval(refreshVisible, 60_000);
        window.addEventListener("focus", refreshVisible);
        return () => {
            mounted.current = false;
            window.clearInterval(timer);
            window.removeEventListener("focus", refreshVisible);
        };
    }, [refreshWallet]);
    return { wallet, walletError, refreshWallet };
}
