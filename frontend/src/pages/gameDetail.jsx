import PhaseReadinessPanel from "../components/game/PhaseReadinessPanel";
import GameHistory from "../components/game/GameHistory";
import historicalOrderLabel from "../components/game/historicalOrderLabel";
import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import api from "../services/api";
import { useAuth } from "../context/AuthContext";


import OrderPanel from "../components/game/OrderPanel";

import {
    getOrders,
    getPreviousResolvedOrders,
    submitOrder,
    getRetreatOrders,
    submitRetreatOrder,
    getAdjustmentOrders,
    getAdjustmentStatus,
    submitAdjustmentOrder,
    cancelAdjustmentOrder,
} from "../services/orders";

import GameMap from "../components/game/GameMap";
import GameSettingsSummary from "../components/game/GameSettingsSummary";
import VictorySummary from "../components/game/VictorySummary";
import GameChat from "../components/game/GameChat";
import DrawProposalPanel from "../components/game/DrawProposalPanel";

const MULTI_COASTS = {
    SPA: ["nc", "sc"],
    STP: ["nc", "sc"],
    BUL: ["ec", "sc"],
};



function GameDetail() {

    const [draftOrderType, setDraftOrderType] = useState(null);
    const [supportedUnit, setSupportedUnit] = useState(null);
    const [convoyedUnit, setConvoyedUnit] = useState(null);
    const [coastSelection, setCoastSelection] = useState(null);

    const [mapOrderMessage, setMapOrderMessage] =
        useState("");

    const [mapOrderError, setMapOrderError] =
        useState("");
    const [selectedUnit, setSelectedUnit] =
        useState(null);
    const [mapTarget, setMapTarget] =
        useState("");
    const { gameId } = useParams();
    const { user } = useAuth();

    const [game, setGame] = useState(null);
    const [focusGameId, setFocusGameId] = useState(null);
    const [focusPane, setFocusPane] = useState("map");
    const [narrowFocus, setNarrowFocus] = useState(() => window.matchMedia?.("(max-width: 850px)").matches ?? false);
    const focusMode = focusGameId === gameId && String(game?.id) === gameId
        && game?.status === "active" && Boolean(game.current_phase);
    const pageRef = useRef(null);
    const focusEntryRef = useRef(null);
    const focusExitRef = useRef(null);
    useEffect(() => {
        const media = window.matchMedia?.("(max-width: 850px)");
        const update = (event) => setNarrowFocus(event.matches);
        media?.addEventListener("change", update);
        return () => media?.removeEventListener("change", update);
    }, []);
    useEffect(() => {
        if (!focusMode) return;
        const bodyOverflow = document.body.style.overflow;
        const htmlOverflow = document.documentElement.style.overflow;
        const entry = focusEntryRef.current;
        const page = pageRef.current;
        document.body.style.overflow = "hidden";
        document.documentElement.style.overflow = "hidden";
        focusExitRef.current?.focus();
        const keydown = (event) => {
            if (event.key === "Escape") {
                event.preventDefault();
                setFocusGameId(null);
            } else if (event.key === "Tab") {
                const controls = [...pageRef.current.querySelectorAll('button:not(:disabled), a[href], input:not(:disabled), textarea:not(:disabled), select:not(:disabled), [tabindex="0"]')]
                    .filter((node) => node.getClientRects().length && !node.closest('[hidden]'));
                const first = controls[0], last = controls.at(-1);
                if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
                if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
            }
        };
        document.addEventListener("keydown", keydown);
        return () => {
            document.body.style.overflow = bodyOverflow;
            document.documentElement.style.overflow = htmlOverflow;
            document.removeEventListener("keydown", keydown);
            // After React has restored normal visibility (or rendered the result).
            queueMicrotask(() => (entry?.isConnected ? entry : page)?.focus());
        };
    }, [focusMode]);
    const [readiness, setReadiness] = useState(null);
    const ordersLocked = !["retreat", undefined].includes(game?.current_phase?.phase_type)
        && readiness?.phase?.id === game?.current_phase?.id
        && (readiness.is_ready || readiness.pending || readiness.phase_resolved);
    const handleReadinessChange = (value) => {
        setReadiness(value);
        if (value.is_ready || value.pending) {
            setSelectedUnit(null);
            setMapTarget("");
            setDraftOrderType(null);
            setSupportedUnit(null);
            setConvoyedUnit(null);
            setCoastSelection(null);
        }
    };
    const [tabSelection, setTabSelection] = useState(null);
    const [unreadCount, setUnreadCount] = useState(0);
    const tabScope = gameId + ":" + game?.status;
    const activeTab = tabSelection?.scope === tabScope ? tabSelection.tab : "game";
    const chatVisible = focusMode ? (!narrowFocus || focusPane === "chat") : activeTab === "diplomacy";
    const historyVisited = tabSelection?.scope === tabScope && tabSelection.historyVisited;
    const selectTab = (tab) => setTabSelection({
        scope: tabScope, tab, historyVisited: historyVisited || tab === "history",
    });
    const [previousHistory, setPreviousHistory] = useState(null);
    // Cache is scoped to the game and current phase; stale requests cannot replace it.
    const historyKey = `${gameId}:${game?.status}:${game?.current_phase?.id ?? "none"}`;
    const history = previousHistory?.key === historyKey ? previousHistory : null;
    const showPreviousOrders = history?.show === true;
    const togglePreviousOrders = async () => {
        if (history?.show || history?.data || history?.loading) {
            setPreviousHistory({ ...history, show: !history.show });
            return;
        }
        setPreviousHistory({ key: historyKey, show: true, loading: true, error: "", data: null });
        try {
            const data = await getPreviousResolvedOrders(gameId);
            setPreviousHistory((current) => current?.key === historyKey
                ? { ...current, loading: false, data } : current);
        } catch (error) {
            setPreviousHistory((current) => current?.key === historyKey
                ? { ...current, loading: false, error: error.response?.data?.detail || "Historické rozkazy se nepodařilo načíst." } : current);
        }
    };
    const isRetreat = game?.current_phase?.phase_type === "retreat";
    const isAdjustment = game?.current_phase?.phase_type === "adjustment";
    const [adjustmentStatus, setAdjustmentStatus] = useState(null);
    const [adjustmentSaving, setAdjustmentSaving] = useState(false);
    const [loading, setLoading] = useState(true);
    const [resolving, setResolving] = useState(false);

    const [error, setError] = useState("");
    const [message, setMessage] = useState("");
    const [orders, setOrders] = useState([]);
    const [ordersLoading, setOrdersLoading] =
        useState(false);

    const loadGame = async () => {
        try {
            const response = await api.get(`games/${gameId}/`);

            if (game?.current_phase?.id !== response.data.current_phase?.id) {
                setOrders([]);
                setAdjustmentStatus(null);
                setMapOrderError("");
                setMapOrderMessage("");
                setSelectedUnit(null);
                setDraftOrderType(null);
                setSupportedUnit(null);
                setConvoyedUnit(null);
                setMapTarget("");
                setCoastSelection(null);
            }
            setGame(response.data);
        } catch (error) {
            console.error(error);

            if (error.response?.status === 404) {
                setError(
                    "Hra neexistuje nebo do ní nemáš přístup."
                );
            } else {
                setError("Nepodařilo se načíst hru.");
            }
        } finally {
            setLoading(false);
        }
    };


    const loadOrders = async () => {
        try {
            setOrdersLoading(true);

            let data;
            if (isAdjustment) {
                const [savedOrders, status] = await Promise.all([
                    getAdjustmentOrders(gameId), getAdjustmentStatus(gameId),
                ]);
                data = savedOrders;
                setAdjustmentStatus(status);
            } else {
                data = await (isRetreat ? getRetreatOrders : getOrders)(gameId);
            }


            setOrders(data);

        } catch (error) {
            if (isAdjustment) setAdjustmentStatus(null);
            setMapOrderError("Nepodařilo se načíst rozkazy.");
            console.error(
                "Nepodařilo se načíst rozkazy:",
                error
            );

        } finally {
            setOrdersLoading(false);
        }
    };


        const handleOrderSaved = async () => {
            setConvoyedUnit(null);
            setSupportedUnit(null);
            setSelectedUnit(null);
            setDraftOrderType(null);
            setMapTarget("");
            setCoastSelection(null);
            await loadOrders();
        };




        useEffect(() => {
            loadGame();
        }, [gameId]);

        useEffect(() => {
            if (
                game?.status === "active" &&
                ["movement", "retreat", "adjustment"].includes(game?.current_phase?.phase_type)
            ) {
                loadOrders();
            }
        }, [
            gameId,
            game?.status,
            game?.current_phase?.id,
            game?.current_phase?.phase_type,
        ]);



    const saveMapOrder = async (data) => {
        if (ordersLocked) return;
        if (isAdjustment && (adjustmentSaving || resolving)) return;
        if (isAdjustment) setAdjustmentSaving(true);
        setMapOrderError("");
        setMapOrderMessage("");

        try {
            const savedOrder = await (isAdjustment ? submitAdjustmentOrder : isRetreat ? submitRetreatOrder : submitOrder)(
                gameId,
                data
            );

            const retreatResolved = isRetreat && savedOrder.phase_resolved === true;
            if (retreatResolved) {
                setOrders([]);
            } else {
                await loadOrders();
            }

            setDraftOrderType(null);
            setMapTarget("");
            setSupportedUnit(null);
            setConvoyedUnit(null);
            setCoastSelection(null);

            // Po úspěšném uložení výběr zavřeme.
            // Bílý okraj a šipka už ukážou uložený stav.
            setSelectedUnit(null);

            if (retreatResolved) {
                await loadGame();
                setMapOrderMessage("Poslední ústupový rozkaz byl uložen a fáze byla vyhodnocena.");
            } else {
                setMapOrderMessage("Rozkaz byl uložen.");
            }

        } catch (error) {
            console.error(error);

            const backendData =
                error.response?.data;

            if (backendData) {
                setMapOrderError(
                    typeof backendData === "string"
                        ? backendData
                        : Object.values(backendData).flat().join(" ")
                );
            } else {
                setMapOrderError(
                    "Rozkaz se nepodařilo uložit."
                );
            }
        } finally {
            if (isAdjustment) setAdjustmentSaving(false);
        }
    };

    const handleCancelAdjustment = async (orderId) => {
        if (ordersLocked) return;
        if (adjustmentSaving || resolving) return;
        setAdjustmentSaving(true);
        setMapOrderError("");
        setMapOrderMessage("");
        try {
            await cancelAdjustmentOrder(gameId, orderId);
            setSelectedUnit(null);
            setMapTarget("");
            setDraftOrderType(null);
            setConvoyedUnit(null);
            setCoastSelection(null);
            await loadOrders();
            setMapOrderMessage("Rozkaz byl zrušen. Můžeš zadat nový.");
        } catch (error) {
            setMapOrderError(error.response?.data?.detail || "Rozkaz se nepodařilo zrušit.");
        } finally {
            setAdjustmentSaving(false);
        }
    };

    const handleBuild = async (unitType) => {
        if (ordersLocked) return;
        const center = adjustmentStatus?.buildable_home_centers.find((item) => item.code === mapTarget);
        if (!center || adjustmentSaving || resolving || adjustmentStatus.builds_remaining <= 0) return;
        if (unitType === "fleet" && center.fleet_coast_codes.length) {
            setCoastSelection({ mode: "build", provinceCode: center.code, options: center.fleet_coast_codes });
            return;
        }
        await saveMapOrder({ order_type: "build", unit_type: unitType, province: center.code });
    };


    const handleMapProvinceClick = async (
        provinceCode,
        clickedUnit
    ) => {
        if (ordersLocked) return;
        if (isAdjustment) {
            if (adjustmentSaving || !adjustmentStatus || adjustmentStatus.builds_remaining <= 0) return;
            if (!adjustmentStatus.buildable_home_centers.some((center) => center.code === provinceCode)) return;
            setMapTarget(provinceCode);
            setSelectedUnit(null);
            setDraftOrderType(null);
            setConvoyedUnit(null);
            setCoastSelection(null);
            setMapOrderError("");
            return;
        }
        if (!selectedUnit) {
            return;
        }

        setMapOrderError("");

        if (game.current_phase.phase_type === "movement") {
            if (draftOrderType === "move-convoy") {
                setMapTarget(provinceCode);
                await saveMapOrder({ unit_id: selectedUnit.id, order_type: "move",
                    target: provinceCode, via_convoy: true });
                return;
            }
            if (draftOrderType === "convoy-unit") {
                if (!clickedUnit || clickedUnit.unit_type !== "army") {
                    setMapOrderError("Pro CONVOY klikni na armádu, kterou chceš konvojovat.");
                    return;
                }
                setConvoyedUnit(clickedUnit);
                setDraftOrderType("convoy-target");
                return;
            }
            if (draftOrderType === "convoy-target" && convoyedUnit) {
                setMapTarget(provinceCode);
                await saveMapOrder({ unit_id: selectedUnit.id, order_type: "convoy",
                    convoyed_unit_id: convoyedUnit.id, convoy_target: provinceCode });
                return;
            }
        }

        // MOVE
if (draftOrderType === "move" || draftOrderType === "retreat") {
    setMapTarget(provinceCode);
    setCoastSelection(null);

    const coastOptions =
        MULTI_COASTS[provinceCode];

    if (
        selectedUnit.unit_type === "fleet" &&
        coastOptions
    ) {
        setCoastSelection({
            mode: draftOrderType,
            provinceCode,
            options: coastOptions,
        });

        return;
    }

    await saveMapOrder({
        unit_id: selectedUnit.id,
        order_type: draftOrderType,
        target: provinceCode,
    });

    return;
}

        // SUPPORT - nejdřív vybírám jednotku
        if (draftOrderType === "support-unit") {
            if (!clickedUnit) {
                setMapOrderError(
                    "Pro SUPPORT nejdřív klikni na jednotku."
                );

                return;
            }

            if (clickedUnit.id === selectedUnit.id) {
                setMapOrderError(
                    "Jednotka nemůže podporovat sama sebe."
                );

                return;
            }

            setSupportedUnit(clickedUnit);
            setDraftOrderType("support-mode");

            return;
        }

        // SUPPORT MOVE - vybírám cíl
if (
    draftOrderType === "support-target"
) {
    if (!supportedUnit) {
        return;
    }

    setMapTarget(provinceCode);

    const coastOptions =
        MULTI_COASTS[provinceCode];

    if (
        supportedUnit.unit_type === "fleet" &&
        coastOptions
    ) {
        setCoastSelection({
            mode: "support",
            provinceCode,
            options: coastOptions,
        });

        return;
    }

    await saveMapOrder({
        unit_id: selectedUnit.id,
        order_type: "support",
        supported_unit_id:
            supportedUnit.id,
        support_target:
            provinceCode,
    });

    return;
}
    };


const handleCoastSelect = async (coastCode) => {
        if (ordersLocked) return;
    if (isAdjustment && coastSelection?.mode === "build") {
        await saveMapOrder({
            order_type: "build", unit_type: "fleet",
            province: coastSelection.provinceCode, coast_code: coastCode,
        });
        return;
    }
    if (
        !coastSelection ||
        !selectedUnit
    ) {
        return;
    }

    const {
        mode,
        provinceCode,
    } = coastSelection;

    if (mode === "move" || mode === "retreat") {
        await saveMapOrder({
            unit_id: selectedUnit.id,
            order_type: mode,
            target: provinceCode,
            target_coast_code:
                coastCode,
        });

        return;
    }

    if (
        mode === "support" &&
        supportedUnit
    ) {
        await saveMapOrder({
            unit_id: selectedUnit.id,
            order_type: "support",
            supported_unit_id:
                supportedUnit.id,
            support_target:
                provinceCode,
            support_target_coast_code:
                coastCode,
        });
    }
};




    const handleMapOrderType = async (orderType) => {
        if (ordersLocked) return;
        if (!selectedUnit) {
            return;
        }

        setMapOrderError("");
        setMapOrderMessage("");
        setMapTarget("");
        setSupportedUnit(null);
        setConvoyedUnit(null);
        setCoastSelection(null);

        if (isAdjustment) {
            if (orderType === "disband" && !selectedUnit.is_dislodged && adjustmentStatus?.disbands_remaining > 0) {
                await saveMapOrder({ order_type: "disband", unit_id: selectedUnit.id });
            }
            return;
        }
        if (isRetreat) {
            if (!selectedUnit.is_dislodged) return;
            if (orderType === "disband") {
                await saveMapOrder({ unit_id: selectedUnit.id, order_type: "disband" });
            } else if (orderType === "retreat") {
                setDraftOrderType("retreat");
            }
            return;
        }

        if (game.current_phase.phase_type !== "movement") return;
        if (orderType === "move-convoy" && selectedUnit.unit_type === "army" && selectedUnit.province_type === "coastal") {
            setDraftOrderType("move-convoy");
            return;
        }
        if (orderType === "convoy" && selectedUnit.unit_type === "fleet" && selectedUnit.province_type === "sea") {
            setDraftOrderType("convoy-unit");
            return;
        }

        if (orderType === "hold") {
            await saveMapOrder({
                unit_id: selectedUnit.id,
                order_type: "hold",
            });

            return;
        }

        if (orderType === "move") {
            setDraftOrderType("move");
            return;
        }

        if (orderType === "support") {
            setDraftOrderType("support-unit");
        }
    };


    const handleSupportModeSelect = async (mode) => {
        if (ordersLocked) return;
        if (!selectedUnit || !supportedUnit) {
            return;
        }

        if (mode === "hold") {
            await saveMapOrder({
                unit_id: selectedUnit.id,
                order_type: "support",
                supported_unit_id: supportedUnit.id,
            });

            return;
        }

        if (mode === "move") {
            setMapTarget("");
            setDraftOrderType("support-target");
        }
    };


    {draftOrderType === "support-mode" &&
        supportedUnit && (
            <div>
                <p>
                    Podporovaná jednotka:{" "}
                    <strong>
                        {supportedUnit.unit_type === "army"
                            ? "A"
                            : "F"}{" "}
                        {supportedUnit.province_name}
                    </strong>
                </p>

                <button
                    onClick={() =>
                        saveMapOrder({
                            unit_id:
                                selectedUnit.id,

                            order_type:
                                "support",

                            supported_unit_id:
                                supportedUnit.id,
                        })
                    }
                >
                    Podpořit HOLD
                </button>

                {" "}

                <button
                    onClick={() => {
                        setDraftOrderType(
                            "support-target"
                        );

                        setMapTarget("");
                    }}
                >
                    Podpořit MOVE
                </button>
            </div>
        )}




    const handleResolvePhase = async () => {
        if (
            resolving || adjustmentSaving ||
            game?.status !== "active" ||
            game?.current_phase?.status !== "open" ||
            game.manual_resolve_allowed !== true
        ) {
            return;
        }

        const endpoints = {
            movement: "resolve",
            retreat: "resolve-retreat",
            adjustment: "resolve-adjustment",
        };
        const endpoint = endpoints[game.current_phase.phase_type];

        setError("");
        setMessage("");

        if (!endpoint) {
            setError("Tento typ fáze nelze ručně vyhodnotit.");
            return;
        }

        setResolving(true);

        try {
            await api.post(`orders/games/${gameId}/${endpoint}/`);

            setOrders([]);
            setAdjustmentStatus(null);
            setSelectedUnit(null);
            setMapTarget("");
            setDraftOrderType(null);
            setSupportedUnit(null);
            setConvoyedUnit(null);
            setCoastSelection(null);
            setMapOrderError("");
            setMapOrderMessage("");

            await loadGame();
            setMessage("Fáze byla vyhodnocena.");
        } catch (error) {
            setError(
                error.response?.data?.detail ||
                "Fázi se nepodařilo vyhodnotit."
            );
        } finally {
            setResolving(false);
        }
    };


    const handleStartGame = async () => {
        setError("");
        setMessage("");

        try {
            const response = await api.post(
                `games/${gameId}/start/`
            );

            setGame(response.data);
            setMessage("Hra byla spuštěna.");

        } catch (error) {
            console.error(error);

            const backendMessage =
                error.response?.data?.detail;

            if (backendMessage) {
                setError(backendMessage);
            } else {
                setError("Hru se nepodařilo spustit.");
            }
        }
    };


    if (loading) {
        return <p>Načítání hry...</p>;
    }


    if (!game) {
        return (
            <div>
                <p>{error}</p>

                <Link to="/">
                    ← Zpět na hlavní stránku
                </Link>
            </div>
        );
    }


    const previousOrdersPanel = (
        <section>
            <button type="button" onClick={togglePreviousOrders}>
                {showPreviousOrders ? "Skrýt poslední rozkazy" : "Zobrazit poslední rozkazy"}
            </button>
            {showPreviousOrders && <>
                {history.loading && <p>Načítání posledních rozkazů...</p>}
                {history.error && <p role="alert">{history.error}</p>}
                {history.data && (!history.data.history_available
                    ? <p>Pro předchozí fázi nejsou historická data k dispozici.</p>
                    : <>
                        <h3>Poslední vyhodnocená fáze: {history.data.phase.season_name} {history.data.phase.year} — {history.data.phase.phase_type_name}</h3>
                        <p>Historický náhled — mapa je pouze ke čtení.</p>
                        <ul>{history.data.orders.map((order, index) => <li key={`${order.id}-${index}`}
                            style={{ color: order.result === "failed" ? "#dc2626" : undefined }}>
                            {order.result === "failed" ? "✗" : "✓"} {order.country}: {historicalOrderLabel(order)}
                            {order.result === "failed" && ` — ${order.result_reason}`}
                        </li>)}</ul>
                    </>)}
            </>}
        </section>
    );

    const isCreator =
        game.creator === user?.username;

    const currentPlayer = game.players.find(
    (player) => player.username === user?.username
    );

    const myUnits = game.units?.filter(
        (unit) => unit.owner_username === user?.username
    ) ?? [];
    const orderableUnits = isRetreat
        ? myUnits.filter((unit) => unit.is_dislodged)
        : isAdjustment
            ? myUnits.filter((unit) => !unit.is_dislodged && adjustmentStatus?.disbands_remaining > 0 && !orders.some((order) => order.saved_unit_id === unit.id))
            : myUnits;
    const buildableCenters = isAdjustment && adjustmentStatus?.builds_remaining > 0
        ? adjustmentStatus.buildable_home_centers : [];






    const gameInfo = <>
        <p>Zakladatel: <strong>{game.creator}</strong></p>
        <h3>Hráči</h3>
            <ul>
                {game.players.map((player) => (
                    <li key={player.id}>
                        <strong>{player.username}</strong>

                        {player.username === game.creator &&
                            " (zakladatel)"
                        }

                        {player.country_name && (
                            <>
                                {" — "}
                                {player.country_name}
                            </>
                        )}
                    </li>
                ))}
            </ul>
        <GameSettingsSummary game={game} />
        {game.status !== "waiting" && !game.is_public && game.invite_code &&
            <p>Pozvánka: <code className="game-invite-code">{game.invite_code}</code></p>}
    </>;
    const hasTabs = ["active", "finished"].includes(game.status);
    const tabs = [{ id: "game", label: game.status === "finished" ? "Výsledek" : "Hra" },
        ...(currentPlayer ? [{ id: "diplomacy", label: "Diplomacie" }, { id: "history", label: "Historie" }] : [])];
    const tabKeyDown = (event, index) => {
        let next;
        if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
        else if (event.key === "ArrowLeft") next = (index + tabs.length - 1) % tabs.length;
        else if (event.key === "Home") next = 0;
        else if (event.key === "End") next = tabs.length - 1;
        else return;
        event.preventDefault();
        selectTab(tabs[next].id);
        event.currentTarget.parentElement.querySelectorAll('[role="tab"]')[next].focus();
    };

    const mapFeedback = (
        <>
        {(draftOrderType === "move" || draftOrderType === "retreat") && (
            <p>
                Klikni na cílovou provincii.
            </p>
        )}

        {draftOrderType === "convoy-unit" && <p>Klikni na armádu, kterou chceš konvojovat.</p>}
        {(draftOrderType === "convoy-target" || draftOrderType === "move-convoy") &&
            <p>Klikni na cílovou pobřežní provincii konvoje.</p>}
        {convoyedUnit && <p>Konvojovaná armáda (tyrkysové označení): {convoyedUnit.province_name} — {convoyedUnit.country_name}</p>}

        {draftOrderType === "support-unit" && (
            <p>
                Klikni na jednotku, kterou chceš podporovat.
            </p>
        )}

        {draftOrderType === "support-target" && (
            <p>
                Klikni na cílovou provincii podporovaného pohybu.
            </p>
        )}

        {mapOrderError && (
            <p className="map-feedback-error" role="alert">
                {mapOrderError}
            </p>
        )}

        {mapOrderMessage && (
            <p className="map-feedback-success" role="status">
                {mapOrderMessage}
            </p>
        )}


        {selectedUnit && (
            <p>
                Vybraná jednotka:{" "}
                <strong>
                    {selectedUnit.unit_type === "army"
                        ? "A"
                        : "F"}{" "}
                    {selectedUnit.province_name}
                </strong>
            </p>
        )}

        {mapTarget && (
            <p>
                Vybraný cíl:{" "}
                <strong>{mapTarget}</strong>
            </p>
        )}
        </>
    );

    return (
        <div ref={pageRef} className={`game-detail-page${focusMode ? " focus-mode" : ""}`}
            role={focusMode ? "dialog" : undefined} aria-modal={focusMode ? true : undefined}
            aria-label={focusMode ? "Herní režim" : undefined} tabIndex={focusMode ? undefined : -1}>
            <div className="focus-toolbar" hidden={!focusMode}>
                <div><div className="focus-title"><strong title={game.name}>{game.name}</strong>{currentPlayer?.country_name && <span>{currentPlayer.country_name}</span>}</div>
                    {game.current_phase && <span>{game.current_phase.season_name} {game.current_phase.year} — {game.current_phase.phase_type_name}
                        {game.current_phase.deadline && " · Deadline: " + new Date(game.current_phase.deadline).toLocaleString("cs-CZ")}</span>}
                    {readiness?.phase?.id === game.current_phase?.id && readiness?.readiness_supported &&
                        <span className="focus-ready"> · Připraveno: {readiness.ready_count} / {readiness.required_count}{readiness.is_ready && " · ✓ Hotovo"}</span>}
                </div>
                <div className="focus-mobile-switch" hidden={!narrowFocus} aria-label="Zobrazení herního režimu">
                    <button type="button" aria-pressed={focusPane === "map"} onClick={() => setFocusPane("map")}>Mapa</button>
                    <button type="button" aria-pressed={focusPane === "chat"} onClick={() => setFocusPane("chat")}>Chat{unreadCount > 0 && ` (${unreadCount})`}</button>
                </div>
                <button type="button" ref={focusExitRef} onClick={() => setFocusGameId(null)}>Ukončit herní režim</button>
            </div>
            <header className="game-header">
                <Link to="/">← Zpět na moje hry</Link>
                <h1>{game.name}</h1>
                {hasTabs && <div className="game-header-meta">
                    {game.status === "finished" ? <span>Dokončena{game.finished_at && " · " + new Date(game.finished_at).toLocaleString("cs-CZ")}</span>
                        : <span>{currentPlayer?.country_name}{game.current_phase && " · " + game.current_phase.season_name + " " + game.current_phase.year + " · " + game.current_phase.phase_type_name}</span>}
                    <span>Hráči: {game.players.length}/{game.max_players}</span>
                </div>}
            </header>
            {error && <p role="alert">{error}</p>}
            {message && <p role="status">{message}</p>}
            {hasTabs ? <details className="game-info-details"><summary>Informace o hře</summary>{gameInfo}</details> : gameInfo}
            {hasTabs && <div className="game-tabs" role="tablist" aria-label="Sekce hry">
                {tabs.map((tab, index) => <button key={tab.id} type="button" role="tab"
                    className="game-tab" id={"game-tab-" + tab.id} aria-controls={"game-panel-" + tab.id}
                    aria-selected={activeTab === tab.id} tabIndex={activeTab === tab.id ? 0 : -1}
                    onKeyDown={(event) => tabKeyDown(event, index)} onClick={() => selectTab(tab.id)}>
                    {tab.label}{tab.id === "diplomacy" && unreadCount > 0 && <span className="tab-badge" aria-label={unreadCount + " nepřečtených zpráv"}>{unreadCount}</span>}
                </button>)}
            </div>}

            {game.status === "waiting" && (
                <>
                    <hr />

                    <h2>Lobby</h2>

                    {isCreator ? (
                        <>
                            <p>
                                Jsi zakladatel této hry.
                            </p>

                            <button
                                onClick={handleStartGame}
                                disabled={
                                    game.players.length < 2
                                }
                            >
                                Spustit hru
                            </button>

                            {game.players.length < 2 && (
                                <p>
                                    Pro spuštění jsou potřeba
                                    alespoň 2 hráči.
                                </p>
                            )}
                        </>
                    ) : (
                        <p>
                            Čeká se, až zakladatel
                            spustí hru.
                        </p>
                    )}
                </>
            )}

            {hasTabs && <section className="game-tab-panel" role="tabpanel" id="game-panel-game"
                aria-labelledby={focusMode ? undefined : "game-tab-game"} hidden={activeTab !== "game"} tabIndex={focusMode ? -1 : 0}>
            {game.status === "finished" && (
                <section className="victory-screen">
                    <VictorySummary game={game} />
                    <section className="final-map-section" aria-labelledby="final-map-title">
                        <h3 id="final-map-title">Konečný stav mapy</h3>
                        {previousOrdersPanel}
                        <GameMap showHistoricalOrders={showPreviousOrders} historicalOrders={history?.data?.orders ?? []} phaseType="finished" units={game.units ?? []}
                            supplyCenters={game.supply_centers ?? []} />
                    </section>
                </section>
            )}

            {game.status === "active" && (
                <>
                    {game.current_phase ? (
                        <div className="active-game-content">
                            <section className="game-phase-card">
                                <h2>{game.current_phase.season_name} {game.current_phase.year} — {game.current_phase.phase_type_name}</h2>
                                {currentPlayer && <p>Tvůj stát: <strong>{currentPlayer.country_name} ({currentPlayer.country})</strong></p>}
                                <p>Deadline: <strong>{new Date(game.current_phase.deadline).toLocaleString("cs-CZ")}</strong></p>
                                <p>Stav fáze: {game.current_phase.status}</p>
                                <button type="button" ref={focusEntryRef} onClick={() => { setFocusPane("map"); setFocusGameId(gameId); }}>Mapa na celou obrazovku</button>
                            {game.manual_resolve_allowed === true && (
                                <button
                                    type="button"
                                    onClick={handleResolvePhase}
                                    disabled={resolving || adjustmentSaving}
                                >
                                    {resolving
                                        ? "Vyhodnocuji..."
                                        : "Vyhodnotit fázi nyní"}
                                </button>
                            )}

                            </section>
                            {currentPlayer && <PhaseReadinessPanel
                                key={"ready:" + game.id + ":" + game.current_phase.id + ":" + currentPlayer.id}
                                gameId={game.id} phaseId={game.current_phase.id} orders={orders}
                                onChange={handleReadinessChange} onPhaseChange={loadGame} />}
                            {currentPlayer && <DrawProposalPanel key={"draw:" + game.id + ":" + currentPlayer.id} gameId={game.id} currentPlayer={currentPlayer} onGameFinished={loadGame} />}
                            <details className="game-unit-details"><summary>Moje jednotky ({myUnits.length})</summary>

                            {myUnits.length > 0 ? (
                                <ul>
                                    {myUnits.map((unit) => (
                                        <li key={unit.id}>
                                            <strong>
                                                {unit.unit_type === "army"
                                                    ? "A"
                                                    : "F"}
                                            </strong>
                                            {" "}
                                            {unit.province_name}

                                            {unit.coast &&
                                                ` (${unit.coast.toUpperCase()})`
                                            }
                                        </li>
                                    ))}
                                </ul>
                            ) : (
                                <p>Nemáš žádné jednotky.</p>
                            )}


                            </details>

                            {isAdjustment && (
                                <section>
                                    <h3>Zimní úpravy</h3>
                                    {ordersLoading && <p>Načítání zimních úprav...</p>}
                                    {adjustmentStatus && <>
                                        <p>Supply centra: {adjustmentStatus.supply_center_count} — Jednotky: {adjustmentStatus.unit_count}</p>
                                        {adjustmentStatus.delta > 0 && <>
                                            <p>Můžeš postavit až {adjustmentStatus.build_count} jednotek. Zbývá: {adjustmentStatus.builds_remaining}. Stavby jsou nepovinné.</p>
                                            <p>Vyber zvýrazněné domácí centrum na mapě nebo níže.</p>
                                            {buildableCenters.map((center) => <button type="button" key={center.code} disabled={ordersLocked || adjustmentSaving} onClick={() => handleMapProvinceClick(center.code)}>{center.name} ({center.code})</button>)}
                                            {buildableCenters.length === 0 && <p>Žádné další volné domácí centrum pro stavbu.</p>}
                                        </>}
                                        {adjustmentStatus.delta < 0 && <>
                                            <p>Musíš rozpustit {adjustmentStatus.disband_count} jednotek. Zbývá zadat: {adjustmentStatus.disbands_remaining}.</p>
                                            <p>Vyber vlastní jednotku na mapě a zvol D.</p>
                                        </>}
                                        {adjustmentStatus.delta === 0 && <p>Nemáš žádné zimní úpravy.</p>}
                                    </>}
                                    <h4>Uložené zimní rozkazy</h4>
                                    <ul>{orders.map((order) => {
                                        const unit = game.units.find((item) => item.id === order.saved_unit_id);
                                        const label = order.order_type === "build"
                                            ? `BUILD ${order.unit_type === "army" ? "A" : "F"} ${order.province_code}${order.saved_coast_code ? ` (${order.saved_coast_code.toUpperCase()})` : ""}`
                                            : `DISBAND ${unit?.unit_type === "army" ? "A" : "F"} ${unit?.province_code ?? "?"}`;
                                        return <li key={order.id}>{label}{" "}<button type="button" disabled={ordersLocked || adjustmentSaving || resolving} onClick={() => handleCancelAdjustment(order.id)}>Zrušit</button></li>;
                                    })}</ul>
                                    <p>Pro změnu uložený rozkaz zruš a zadej nový.</p>
                                </section>
                            )}

                            {isRetreat && (
                                <section>
                                    <h3>Ústupy vytlačených jednotek</h3>
                                    <p>Vyber jednotku na mapě nebo níže. R = ústup, D = rozpuštění.
                                        Jednotka bez rozkazu bude při vyhodnocení automaticky rozpuštěna.</p>
                                    {ordersLoading && <p>Načítání rozkazů...</p>}
                                    {orderableUnits.length === 0 && <p>Nemáš žádné vytlačené jednotky.</p>}
                                    <ul>
                                        {orderableUnits.map((unit) => {
                                            const order = orders.find((item) => item.saved_unit_id === unit.id);
                                            return (
                                                <li key={unit.id}>
                                                    <button type="button" onClick={() => {
                                                        setSelectedUnit(unit);
                                                        setDraftOrderType(null);
                                                        setMapTarget("");
                                                        setSupportedUnit(null);
                                                        setConvoyedUnit(null);
                                                        setCoastSelection(null);
                                                        setMapOrderError("");
                                                        setMapOrderMessage("");
                                                    }}>
                                                        {unit.unit_type === "army" ? "A" : "F"} {unit.province_name}
                                                        {unit.coast && ` (${unit.coast.toUpperCase()})`}
                                                    </button>
                                                    {" — "}{order
                                                        ? order.order_type === "disband"
                                                            ? "Uloženo: DISBAND"
                                                            : `Uloženo: RETREAT → ${order.target_code}${order.target_coast ? ` (${order.target_coast.toUpperCase()})` : ""}`
                                                        : "Čeká na rozhodnutí"}
                                                </li>
                                            );
                                        })}
                                    </ul>
                                </section>
                            )}

                            {previousOrdersPanel}
                            <div className="focus-map-area" hidden={focusMode && narrowFocus && focusPane === "chat"}>
                            <GameMap
                                focusMode={focusMode}
                                ordersLocked={ordersLocked}
                                showHistoricalOrders={showPreviousOrders}
                                historicalOrders={history?.data?.orders ?? []}
                                onBuildTypeSelect={handleBuild}
                                buildableCenters={buildableCenters}
                                phaseType={game.current_phase.phase_type}
                                units={game.units}
                                myUnits={orderableUnits}
                                orders={orders}
                                supplyCenters={
                                    game.supply_centers ?? []
                                }

                                selectedUnit={selectedUnit}
                                supportedUnit={supportedUnit}
                                convoyedUnit={convoyedUnit}
                                selectedTarget={mapTarget}
                                draftOrderType={draftOrderType}

                                coastSelection={coastSelection}

                                onSelectUnit={(unit) => {
                                    if (ordersLocked) return;
                                    if (isAdjustment && adjustmentSaving) return;
                                    setSelectedUnit(unit);

                                    setSupportedUnit(null);

                                    setConvoyedUnit(null);
                                    setMapTarget("");
                                    setDraftOrderType(null);
                                    setCoastSelection(null);

                                    setMapOrderError("");
                                    setMapOrderMessage("");
                                }}

                                onOrderTypeSelect={
                                    handleMapOrderType
                                }

                                onSupportModeSelect={
                                    handleSupportModeSelect
                                }

                                onProvinceClick={
                                    handleMapProvinceClick
                                }

                                onCoastSelect={
                                    handleCoastSelect
                                }
                            />


                            {!focusMode && mapFeedback}
                            </div>
                            <div className="game-secondary-panels" hidden={focusMode}>
                            {game.current_phase?.phase_type === "movement" && (
                                <details className="game-secondary-panel game-manual-orders">
                                    <summary>Ruční zadávání rozkazů ({myUnits.length})</summary>
                                    <p>Alternativní textové zadávání rozkazů.</p>

                                    {ordersLoading ? (
                                        <p>Načítání rozkazů...</p>
                                    ) : (
                                        myUnits.map((unit) => {
                                            const existingOrder = orders.find(
                                                (order) =>
                                                    order.saved_unit_id === unit.id
                                            );

                                            return (
                                                <OrderPanel
                                                    ordersLocked={ordersLocked}
                                                    key={unit.id}
                                                    gameId={gameId}
                                                    unit={unit}
                                                    allUnits={game.units}
                                                    existingOrder={existingOrder}
                                                    onOrderSaved={handleOrderSaved}
                                                />
                                            );
                                        })
                                    )}
                                </details>
                            )}

                                <details className="game-secondary-panel game-all-units"><summary>Všechny jednotky</summary>

                                <ul>
                                    {game.units.map((unit) => (
                                        <li key={unit.id}>
                                            <strong>
                                                {unit.unit_type === "army"
                                                    ? "A"
                                                    : "F"}
                                            </strong>
                                            {" "}
                                            {unit.province_name}

                                            {unit.coast &&
                                                ` (${unit.coast.toUpperCase()})`
                                            }

                                            {" — "}
                                            {unit.country_name}

                                            {" — "}
                                            {unit.owner_username}
                                        </li>
                                    ))}
                                </ul>



                                </details>
                            </div>

                        </div>
                    ) : (
                        <p>
                            Aktivní fáze nebyla nalezena.
                        </p>
                    )}
                </>
            )}
            </section>}
            {focusMode && <aside className={`focus-status-panel${narrowFocus && focusPane === "map" ? " focus-status-overlay" : ""}`} aria-label="Stav a instrukce">{mapFeedback}</aside>}
            {hasTabs && currentPlayer && <section className="game-tab-panel" role="tabpanel" id="game-panel-diplomacy"
                aria-labelledby={focusMode ? undefined : "game-tab-diplomacy"} aria-label={focusMode ? "Diplomacie" : undefined} hidden={!chatVisible} tabIndex={focusMode ? -1 : 0}>
                <GameChat key={"chat:" + game.id + ":" + currentPlayer.id} game={game} currentPlayer={currentPlayer}
                    visible={chatVisible} onUnreadCountChange={setUnreadCount} />
            </section>}
            {hasTabs && currentPlayer && <section className="game-tab-panel" role="tabpanel" id="game-panel-history"
                aria-labelledby="game-tab-history" hidden={activeTab !== "history"} tabIndex={0}>
                {historyVisited && <GameHistory key={"history:" + game.id + ":" + game.current_phase?.id + ":" + game.status} gameId={game.id} embedded />}
            </section>}
        </div>
    );
}


export default GameDetail;
