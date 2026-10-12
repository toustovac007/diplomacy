import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import api from "../services/api";
import { useAuth } from "../context/AuthContext";


import OrderPanel from "../components/game/OrderPanel";

import {
    getOrders,
    submitOrder,
} from "../services/orders";

import GameMap from "../components/game/GameMap";

function GameDetail() {
    const [draftOrderType, setDraftOrderType] =
        useState(null);

    const [supportedUnit, setSupportedUnit] =
        useState(null);

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
    const [loading, setLoading] = useState(true);

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

            const data = await getOrders(
                gameId
            );

            console.log("ORDERS Z API:", data);


            setOrders(data);

        } catch (error) {
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
                game?.current_phase?.phase_type === "movement"
            ) {
                loadOrders();
            }
        }, [
            gameId,
            game?.status,
            game?.current_phase?.id,
        ]);



    const saveMapOrder = async (data) => {
        setMapOrderError("");
        setMapOrderMessage("");

        try {
            await submitOrder(
                gameId,
                data
            );

            await loadOrders();

            setMapOrderMessage(
                "Rozkaz byl uložen."
            );

            setDraftOrderType(null);
            setMapTarget("");
            setSupportedUnit(null);

            // Po úspěšném uložení výběr zavřeme.
            // Bílý okraj a šipka už ukážou uložený stav.
            setSelectedUnit(null);

        } catch (error) {
            console.error(error);

            const backendData =
                error.response?.data;

            if (backendData) {
                setMapOrderError(
                    typeof backendData === "string"
                        ? backendData
                        : JSON.stringify(backendData)
                );
            } else {
                setMapOrderError(
                    "Rozkaz se nepodařilo uložit."
                );
            }
        }
    };



    const handleMapProvinceClick = async (
        provinceCode,
        clickedUnit
    ) => {
        setMapOrderError("");

        if (!selectedUnit) {
            return;
        }

        // =========================
        // MOVE
        // =========================

        if (draftOrderType === "move") {
            setMapTarget(
                provinceCode
            );

            await saveMapOrder({
                unit_id: selectedUnit.id,
                order_type: "move",
                target: provinceCode,
            });

            return;
        }

        // =========================
        // SUPPORT - výběr jednotky
        // =========================

        if (
            draftOrderType ===
            "support-unit"
        ) {
            if (!clickedUnit) {
                setMapOrderError(
                    "Klikni na jednotku, kterou chceš podporovat."
                );

                return;
            }

            if (
                clickedUnit.id ===
                selectedUnit.id
            ) {
                setMapOrderError(
                    "Jednotka nemůže podporovat sama sebe."
                );

                return;
            }

            setSupportedUnit(
                clickedUnit
            );

            setDraftOrderType(
                "support-mode"
            );

            return;
        }

        // =========================
        // SUPPORT MOVE - cíl
        // =========================

        if (
            draftOrderType ===
            "support-target"
        ) {
            if (!supportedUnit) {
                return;
            }

            setMapTarget(
                provinceCode
            );

            await saveMapOrder({
                unit_id: selectedUnit.id,
                order_type: "support",
                supported_unit_id:
                    supportedUnit.id,
                support_target:
                    provinceCode,
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
            setDraftOrderType(
                "support-unit"
            );
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


                            <GameMap
                                units={game.units}
                                myUnits={myUnits}
                                orders={orders}

                                selectedUnit={selectedUnit}
                                selectedTarget={mapTarget}
                                draftOrderType={draftOrderType}

                                onSelectUnit={(unit) => {
                                    setSelectedUnit(unit);

                                    setMapTarget("");
                                    setDraftOrderType(null);
                                    setSupportedUnit(null);

                                    setMapOrderError("");
                                    setMapOrderMessage("");
                                }}

                                onOrderTypeSelect={
                                    handleMapOrderType
                                }

                                onProvinceClick={
                                    handleMapProvinceClick
                                }
                            />


                            {draftOrderType === "move" && (
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