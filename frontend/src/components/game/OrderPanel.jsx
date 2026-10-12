import { useEffect, useState } from "react";

import { submitOrder } from "../../services/orders";

function OrderPanel({
    gameId,
    unit,
    allUnits,
    existingOrder,
    onOrderSaved,
}) {

    const [supportedUnitId, setSupportedUnitId] = useState("");
    const [supportMode, setSupportMode] = useState("hold");
    const [supportTarget, setSupportTarget] = useState("");

    const [orderType, setOrderType] = useState("hold");
    const [target, setTarget] = useState("");

    const [saving, setSaving] = useState(false);
    const [error, setError] = useState("");
    const [message, setMessage] = useState("");



useEffect(() => {
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

        if (existingOrder.support_target_code) {
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

            if (onOrderSaved) {
                onOrderSaved(savedOrder);
            }

        } catch (error) {
            console.error(error);

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

            <form onSubmit={handleSubmit}>
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
                </div>


                {orderType === "move" && (
                    <div>
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