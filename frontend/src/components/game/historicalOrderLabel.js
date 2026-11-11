export default function historicalOrderLabel(order) {
    const unit = order.unit_type === "army" ? "A" : "F";
    const origin = `${order.origin ?? "?"}${order.origin_coast_code ? `/${order.origin_coast_code}` : ""}`;
    const target = `${order.target_code ?? "?"}${order.saved_target_coast ? `/${order.saved_target_coast}` : ""}`;
    if (order.order_type === "build" || order.order_type === "disband") {
        return `${order.order_type.toUpperCase()} ${unit} ${origin}`;
    }
    const prefix = `${unit} ${origin}`;
    if (order.order_type === "support") {
        const action = order.supported_origin === order.support_target_code
            ? "HOLD" : `→ ${order.support_target_code}`;
        return `${prefix} S ${order.supported_unit_type === "army" ? "A" : "F"} ${order.supported_origin} ${action}`;
    }
    if (order.order_type === "convoy") return `${prefix} C A ${order.convoyed_origin} → ${order.convoy_target_code}`;
    if (order.order_type === "hold") return `${prefix} HOLD`;
    return `${prefix}${order.order_type === "retreat" ? " RETREAT" : order.via_convoy ? " VIA CONVOY" : ""} → ${target}`;
}
