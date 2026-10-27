import { useEffect, useState } from "react";

import { submitOrder } from "../../services/orders";

function OrderPanel({
    gameId,
    unit,
    allUnits,
    existingOrder,
    onOrderSaved,
    ordersLocked = false,
}) {

    const [supportedUnitId, setSupportedUnitId] = useState("");
    const [supportMode, setSupportMode] = useState("hold");
    const [supportTarget, setSupportTarget] = useState("");

    const [viaConvoy, setViaConvoy] = useState(false);
    const [convoyedUnitId, setConvoyedUnitId] = useState("");
    const [convoyTarget, setConvoyTarget] = useState("");

    const [orderType, setOrderType] = useState("hold");
    const [target, setTarget] = useState("");

    const [saving, setSaving] = useState(false);
    const [error, setError] = useState("");
    const [message, setMessage] = useState("");



useEffect(() => {
    setViaConvoy(existingOrder?.order_type === "move" && existingOrder.via_convoy === true);
    setConvoyedUnitId(existingOrder?.convoyed_unit_id?.toString() ?? "");
    setConvoyTarget(existingOrder?.convoy_target_code ?? "");
    if (!existingOrder) {
        setOrderType("hold");
        setTarget("");

        setSupportedUnitId("");
        setSupportMode("hold");
        setSupportTarget("");

        return;
    }

    setOrderType(existingOrder.order_type);

    if (existingOrder.order_type === "move") {
        setTarget(
            existingOrder.target_code ?? ""
        );
    } else {
        setTarget("");
    }

    if (existingOrder.order_type === "support") {
        setSupportedUnitId(
            existingOrder.supported_unit_id?.toString() ?? ""
        );

        if (existingOrder.support_target_code && existingOrder.support_target_code !== existingOrder.supported_origin) {
            setSupportMode("move");
            setSupportTarget(
                existingOrder.support_target_code
            );
        } else {
            setSupportMode("hold");
            setSupportTarget("");
        }
    } else {
        setSupportedUnitId("");
        setSupportMode("hold");
        setSupportTarget("");
    }
}, [existingOrder, unit.id]);


    const handleSubmit = async (event) => {
        event.preventDefault();
        if (ordersLocked) return;

        setError("");
        setMessage("");

        const data = {
            unit_id: unit.id,
            order_type: orderType,
        };

        if (orderType === "move") {
            const cleanedTarget = target
                .trim()
                .toUpperCase();

            if (!cleanedTarget) {
                setError(
                    "Zadej kód cílové provincie."
                );
                return;
            }

            data.target = cleanedTarget;
            data.via_convoy = unit.unit_type === "army" && viaConvoy;
        }

        if (orderType === "convoy") {
            if (!convoyedUnitId || !convoyTarget.trim()) {
                setError("Vyber konvojovanou armádu a zadej cílovou provincii.");
                return;
            }
            data.convoyed_unit_id = Number(convoyedUnitId);
            data.convoy_target = convoyTarget.trim().toUpperCase();
        }

        if (orderType === "support") {
            if (!supportedUnitId) {
                setError(
                    "Vyber jednotku, kterou chceš podporovat."
                );
                return;
            }

            data.supported_unit_id =
                Number(supportedUnitId);

            if (supportMode === "move") {
                const cleanedSupportTarget =
                    supportTarget
                        .trim()
                        .toUpperCase();

                if (!cleanedSupportTarget) {
                    setError(
                        "Zadej cílovou provincii podporovaného pohybu."
                    );
                    return;
                }

                data.support_target =
                    cleanedSupportTarget;
            }
        }




        try {
            setSaving(true);

            const savedOrder = await submitOrder(
                gameId,
                data
            );

            console.log("ULOŽENÝ ORDER:", savedOrder);


            if (onOrderSaved) {
                await onOrderSaved(
                    savedOrder
                );
            }

            setMessage(
                "Rozkaz byl uložen."
            );


        } catch (error) {
            console.error("API request failed", error.response?.status);

            const backendData =
                error.response?.data;

            if (backendData) {
                setError(
                    typeof backendData === "string"
                        ? backendData
                        : JSON.stringify(backendData)
                );
            } else {
                setError(
                    "Rozkaz se nepodařilo uložit."
                );
            }

        } finally {
            setSaving(false);
        }
    };


    return (
        <div>
            <h4>
                {unit.unit_type === "army"
                    ? "A"
                    : "F"}{" "}
                {unit.province_name}

                {unit.coast &&
                    `/${unit.coast.toUpperCase()}`
                }
            </h4>

            {ordersLocked && <p>Rozkazy jsou uzamčené, protože jsi označil fázi jako hotovou.</p>}
            <form onSubmit={handleSubmit}>
                <fieldset disabled={ordersLocked} style={{ border: 0, padding: 0, margin: 0 }}>
                <div>
                    <label>
                        <input
                            type="radio"
                            name={`order-${unit.id}`}
                            value="hold"
                            checked={orderType === "hold"}
                            onChange={() =>
                                setOrderType("hold")
                            }
                        />

                        HOLD
                    </label>

                    {" "}

                    <label>
                        <input
                            type="radio"
                            name={`order-${unit.id}`}
                            value="move"
                            checked={orderType === "move"}
                            onChange={() =>
                                setOrderType("move")
                            }
                        />

                        MOVE
                    </label>



                    <label>
                        <input
                            type="radio"
                            name={`order-${unit.id}`}
                            value="support"
                            checked={orderType === "support"}
                            onChange={() =>
                                setOrderType("support")
                            }
                        />

                        SUPPORT
                    </label>
                    {unit.unit_type === "fleet" && unit.province_type === "sea" && (
                        <label>
                            <input type="radio" name={`order-${unit.id}`} value="convoy"
                                checked={orderType === "convoy"} onChange={() => setOrderType("convoy")} />
                            CONVOY
                        </label>
                    )}
                </div>


                {orderType === "move" && (
                    <div>
                        {unit.unit_type === "army" && unit.province_type === "coastal" && (
                            <label>
                                <input type="checkbox" checked={viaConvoy}
                                    onChange={(event) => setViaConvoy(event.target.checked)} />
                                Via convoy (přes konvoj)
                            </label>
                        )}
                        <label>
                            Cílová provincie:{" "}

                            <input
                                type="text"
                                value={target}
                                maxLength={3}
                                placeholder="BUR"
                                onChange={(event) =>
                                    setTarget(
                                        event.target.value
                                    )
                                }
                            />
                        </label>
                    </div>
                )}


                {orderType === "convoy" && (
                    <div>
                        <label>
                            Konvojovaná armáda:{" "}
                            <select value={convoyedUnitId} onChange={(event) => setConvoyedUnitId(event.target.value)}>
                                <option value="">-- vyber armádu --</option>
                                {allUnits.filter((other) => other.unit_type === "army").map((other) => (
                                    <option key={other.id} value={other.id}>
                                        A {other.province_name} — {other.country_name}
                                    </option>
                                ))}
                            </select>
                        </label>
                        <label>
                            Cílová pobřežní provincie:{" "}
                            <input type="text" value={convoyTarget} maxLength={3} placeholder="BEL"
                                onChange={(event) => setConvoyTarget(event.target.value)} />
                        </label>
                    </div>
                )}

                {orderType === "support" && (
                    <div>
                        <div>
                            <label>
                                Podporovaná jednotka:{" "}

                                <select
                                    value={supportedUnitId}
                                    onChange={(event) =>
                                        setSupportedUnitId(
                                            event.target.value
                                        )
                                    }
                                >
                                    <option value="">
                                        -- vyber jednotku --
                                    </option>

                                    {allUnits
                                        .filter(
                                            (otherUnit) =>
                                                otherUnit.id !== unit.id
                                        )
                                        .map((otherUnit) => (
                                            <option
                                                key={otherUnit.id}
                                                value={otherUnit.id}
                                            >
                                                {otherUnit.unit_type === "army"
                                                    ? "A"
                                                    : "F"}{" "}
                                                {otherUnit.province_name}
                                                {" — "}
                                                {otherUnit.country_name}
                                            </option>
                                        ))}
                                </select>
                            </label>
                        </div>

                        <div>
                            <label>
                                <input
                                    type="radio"
                                    checked={supportMode === "hold"}
                                    onChange={() =>
                                        setSupportMode("hold")
                                    }
                                />

                                Podpořit HOLD
                            </label>

                            {" "}

                            <label>
                                <input
                                    type="radio"
                                    checked={supportMode === "move"}
                                    onChange={() =>
                                        setSupportMode("move")
                                    }
                                />

                                Podpořit MOVE
                            </label>
                        </div>

                        {supportMode === "move" && (
                            <div>
                                <label>
                                    Cílová provincie:{" "}

                                    <input
                                        type="text"
                                        maxLength={3}
                                        value={supportTarget}
                                        placeholder="BUR"
                                        onChange={(event) =>
                                            setSupportTarget(
                                                event.target.value
                                            )
                                        }
                                    />
                                </label>
                            </div>
                        )}
                    </div>
                )}





                <button
                    type="submit"
                    disabled={saving}
                >
                    {saving
                        ? "Ukládám..."
                        : "Uložit rozkaz"}
                </button>
            </fieldset>
            </form>

            {error && (
                <p>{error}</p>
            )}

            {message && (
                <p>{message}</p>
            )}

            {existingOrder && (
                <p>
                    Aktuálně uložený rozkaz:{" "}
                    <strong>
                        {existingOrder.order_type.toUpperCase()}
                    </strong>

                    {existingOrder.order_type === "move" && existingOrder.via_convoy && " VIA CONVOY"}
                    {existingOrder.order_type === "convoy" &&
                        ` A ${existingOrder.convoyed_origin} → ${existingOrder.convoy_target_code}`}
                    {existingOrder.target_code &&
                        ` → ${existingOrder.target_code}`
                    }
                </p>
            )}

            <hr />
        </div>
    );
}


export default OrderPanel;
