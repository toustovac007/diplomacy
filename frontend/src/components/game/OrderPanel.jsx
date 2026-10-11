import { useEffect, useState } from "react";

import { submitOrder } from "../../services/orders";

function OrderPanel({
    gameId,
    unit,
    existingOrder,
    onOrderSaved,
}) {
    const [orderType, setOrderType] = useState("hold");
    const [target, setTarget] = useState("");

    const [saving, setSaving] = useState(false);
    const [error, setError] = useState("");
    const [message, setMessage] = useState("");



    useEffect(() => {


         console.log(
            "ORDER PANEL:",
            unit.id,
            existingOrder
        );

        if (!existingOrder) {
            setOrderType("hold");
            setTarget("");
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