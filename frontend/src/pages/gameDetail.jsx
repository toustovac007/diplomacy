import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import api from "../services/api";
import { useAuth } from "../context/AuthContext";


import OrderPanel from "../components/game/OrderPanel";

import {
    getOrders,
    submitOrder,
    getRetreatOrders,
    submitRetreatOrder,
    getAdjustmentOrders,
    getAdjustmentStatus,
    submitAdjustmentOrder,
    cancelAdjustmentOrder,
} from "../services/orders";

import GameMap from "../components/game/GameMap";

const MULTI_COASTS = {
    SPA: ["nc", "sc"],
    STP: ["nc", "sc"],
    BUL: ["ec", "sc"],
};


function GameDetail() {

    const [draftOrderType, setDraftOrderType] = useState(null);
    const [supportedUnit, setSupportedUnit] = useState(null);
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

            console.log("ORDERS Z API:", data);


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
        if (adjustmentSaving || resolving) return;
        setAdjustmentSaving(true);
        setMapOrderError("");
        setMapOrderMessage("");
        try {
            await cancelAdjustmentOrder(gameId, orderId);
            setSelectedUnit(null);
            setMapTarget("");
            setDraftOrderType(null);
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
        if (isAdjustment) {
            if (adjustmentSaving || !adjustmentStatus || adjustmentStatus.builds_remaining <= 0) return;
            if (!adjustmentStatus.buildable_home_centers.some((center) => center.code === provinceCode)) return;
            setMapTarget(provinceCode);
            setSelectedUnit(null);
            setDraftOrderType(null);
            setCoastSelection(null);
            setMapOrderError("");
            return;
        }
        if (!selectedUnit) {
            return;
        }

        setMapOrderError("");

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
        if (!selectedUnit) {
            return;
        }

        setMapOrderError("");
        setMapOrderMessage("");
        setMapTarget("");
        setSupportedUnit(null);
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
            game.creator !== user?.username
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


    console.log(
        "MOJE JEDNOTKY:",
        myUnits.map((unit) => ({
            id: unit.id,
            province: unit.province_name,
        }))
    );




    return (
        <div>
            <Link to="/">
                ← Zpět na moje hry
            </Link>

            <h1>{game.name}</h1>

            <p>
                Zakladatel:{" "}
                <strong>{game.creator}</strong>
            </p>

            <p>
                Stav:{" "}
                <strong>{game.status}</strong>
            </p>

            <p>
                Délka kola:{" "}
                <strong>
                    {game.turn_duration_minutes} minut
                </strong>
            </p>

            <p>
                Počet hráčů:{" "}
                <strong>
                    {game.players.length}/{game.max_players}
                </strong>
            </p>


            {error && (
                <p>{error}</p>
            )}

            {message && (
                <p>{message}</p>
            )}


            <hr />

            <h2>Hráči</h2>

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

            {game.status === "active" && (
                <>
                    <hr />

                    <h2>Hra probíhá</h2>


                                    {currentPlayer && (
                    <div>
                        <h3>Tvůj stát</h3>

                        <p>
                            <strong>
                                {currentPlayer.country_name}
                            </strong>
                            {" "}
                            ({currentPlayer.country})
                        </p>
                    </div>
                )}





                    {game.current_phase ? (
                        <div>
                            <h3>
                                {game.current_phase.season_name}{" "}
                                {game.current_phase.year}
                            </h3>

                            <p>
                                Fáze:{" "}
                                <strong>
                                    {game.current_phase.phase_type_name}
                                </strong>
                            </p>

                            <p>
                                Stav:{" "}
                                <strong>
                                    {game.current_phase.status}
                                </strong>
                            </p>

                            {isCreator && game.current_phase.status === "open" && (
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

                            <h3>Moje jednotky</h3>

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


                            {isAdjustment && (
                                <section>
                                    <h3>Zimní úpravy</h3>
                                    {ordersLoading && <p>Načítání zimních úprav...</p>}
                                    {adjustmentStatus && <>
                                        <p>Supply centra: {adjustmentStatus.supply_center_count} — Jednotky: {adjustmentStatus.unit_count}</p>
                                        {adjustmentStatus.delta > 0 && <>
                                            <p>Můžeš postavit až {adjustmentStatus.build_count} jednotek. Zbývá: {adjustmentStatus.builds_remaining}. Stavby jsou nepovinné.</p>
                                            <p>Vyber zvýrazněné domácí centrum na mapě nebo níže.</p>
                                            {buildableCenters.map((center) => <button type="button" key={center.code} disabled={adjustmentSaving} onClick={() => handleMapProvinceClick(center.code)}>{center.name} ({center.code})</button>)}
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
                                        return <li key={order.id}>{label}{" "}<button type="button" disabled={adjustmentSaving || resolving} onClick={() => handleCancelAdjustment(order.id)}>Zrušit</button></li>;
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

                            <GameMap
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
                                selectedTarget={mapTarget}
                                draftOrderType={draftOrderType}

                                coastSelection={coastSelection}

                                onSelectUnit={(unit) => {
                                    if (isAdjustment && adjustmentSaving) return;
                                    setSelectedUnit(unit);

                                    setSupportedUnit(null);
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


                            {(draftOrderType === "move" || draftOrderType === "retreat") && (
                                <p>
                                    Klikni na cílovou provincii.
                                </p>
                            )}

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
                                <p>
                                    {mapOrderError}
                                </p>
                            )}

                            {mapOrderMessage && (
                                <p>
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




                            {game.current_phase?.phase_type === "movement" && (
                                <>
                                    <h3>Rozkazy</h3>

                                    {ordersLoading ? (
                                        <p>Načítání rozkazů...</p>
                                    ) : (
                                        myUnits.map((unit) => {
                                            const existingOrder = orders.find(
                                                (order) =>
                                                    order.saved_unit_id === unit.id
                                            );

                                            console.log(
                                                "PÁROVÁNÍ:",
                                                {
                                                    unitId: unit.id,
                                                    province: unit.province_name,
                                                    orderIds: orders.map(
                                                        (order) => order.saved_unit_id
                                                    ),
                                                    foundOrder: existingOrder,
                                                }
                                            );

                                            return (
                                                <OrderPanel
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
                                </>
                            )}

                                <h3>Všechny jednotky</h3>

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



                            <p>
                                Deadline:{" "}
                                <strong>
                                    {new Date(
                                        game.current_phase.deadline
                                    ).toLocaleString("cs-CZ")}
                                </strong>
                            </p>
                        </div>
                    ) : (
                        <p>
                            Aktivní fáze nebyla nalezena.
                        </p>
                    )}
                </>
            )}
        </div>
    );
}


export default GameDetail;
