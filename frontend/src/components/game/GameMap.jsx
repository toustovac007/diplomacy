import { useEffect, useMemo, useRef, useState } from "react";
import { COUNTRY_COLORS } from "./countryColors";




const SVG_NS = "http://www.w3.org/2000/svg";

const PROVINCE_CODES = [
    "ADR", "AEG", "ALB", "ANK", "APU", "ARM", "BAL", "BAR", "BEL", "BER",
    "BLA", "BOH", "BOT", "BRE", "BUD", "BUL", "BUR", "CLY", "CON", "DEN",
    "EAS", "EDI", "ENG", "FIN", "GAL", "GAS", "GOL", "GRE", "HEL", "HOL",
    "ION", "IRI", "KIE", "LON", "LVN", "LVP", "MAO", "MAR", "MOS", "MUN",
    "NAF", "NAP", "NAO", "NTH", "NWG", "NWY", "PAR", "PIC", "PIE", "POR",
    "PRU", "ROM", "RUH", "RUM", "SER", "SEV", "SIL", "SKA", "SMY", "SPA",
    "STP", "SWE", "SYR", "TRI", "TUN", "TUS", "TYR", "TYS", "UKR", "VEN",
    "VIE", "WAL", "WAR", "WES", "YOR",
];

const PROVINCE_CODE_SET = new Set(PROVINCE_CODES);

const SVG_BASE_IDS = {
    MAO: ["mao", "mid"],
    NAO: ["nao", "nat"],
    NWG: ["nwg", "nrg"],
    TYS: ["tys", "tyn"],
};

const SVG_ID_TO_GAME_CODE = {
    mid: "MAO",
    mao: "MAO",
    nat: "NAO",
    nao: "NAO",
    nrg: "NWG",
    nwg: "NWG",
    tyn: "TYS",
    tys: "TYS",
};



const SUPPLY_CENTER_COLORS = {
    AUS: "#e0b7b0",
    ENG: "#c8aff0",
    FRA: "#9db9ff",
    GER: "#cbbcab",
    ITA: "#9bd49b",
    RUS: "#bcc3d1",
    TUR: "#e3d56f",
};

const NEUTRAL_SUPPLY_CENTER_COLOR =
    "#e6dfb3";

function createSvgElement(name) {
    return document.createElementNS(SVG_NS, name);
}

function getSvgBaseIds(gameCode) {
    if (!gameCode) {
        return [];
    }

    const upper = gameCode.toUpperCase();

    return SVG_BASE_IDS[upper] ?? [
        upper.toLowerCase(),
    ];
}

function normalizeSvgProvinceId(rawId) {
    if (!rawId) {
        return null;
    }

    const normalized = rawId
        .toLowerCase()
        .replace(/^_/, "");

    if (SVG_ID_TO_GAME_CODE[normalized]) {
        return SVG_ID_TO_GAME_CODE[normalized];
    }

    const baseId = normalized.split("-")[0];

    if (SVG_ID_TO_GAME_CODE[baseId]) {
        return SVG_ID_TO_GAME_CODE[baseId];
    }

    const gameCode = baseId.toUpperCase();

    if (PROVINCE_CODE_SET.has(gameCode)) {
        return gameCode;
    }

    return null;
}

function getVisibleProvinceElement(svg, gameCode) {
    for (const baseId of getSvgBaseIds(gameCode)) {
        const element = svg.querySelector(
            `#_${baseId}`
        );

        if (element) {
            return element;
        }
    }

    return null;
}

function shortenLine(from, to, startOffset = 28, endOffset = 30) {
    const dx = to.x - from.x;
    const dy = to.y - from.y;
    const length = Math.hypot(dx, dy);

    if (!length || length <= startOffset + endOffset) {
        return {
            x1: from.x,
            y1: from.y,
            x2: to.x,
            y2: to.y,
        };
    }

    const ux = dx / length;
    const uy = dy / length;

    return {
        x1: from.x + ux * startOffset,
        y1: from.y + uy * startOffset,
        x2: to.x - ux * endOffset,
        y2: to.y - uy * endOffset,
    };
}

function addArrowMarker(defs, id, fill) {
    const marker = createSvgElement("marker");

    marker.setAttribute("id", id);
    marker.setAttribute("viewBox", "0 0 10 10");
    marker.setAttribute("refX", "8");
    marker.setAttribute("refY", "5");
    marker.setAttribute("markerWidth", "8");
    marker.setAttribute("markerHeight", "8");
    marker.setAttribute("orient", "auto-start-reverse");

    const path = createSvgElement("path");

    path.setAttribute("d", "M 0 0 L 10 5 L 0 10 z");
    path.setAttribute("fill", fill);

    marker.appendChild(path);
    defs.appendChild(marker);
}

function drawArrow(
    layer,
    from,
    to,
    {
        dash = "",
        markerId,
        innerStroke = "#111827",
        outerStroke = "#ffffff",
    }
) {
    const line = shortenLine(from, to);

    const outer = createSvgElement("line");

    outer.setAttribute("x1", String(line.x1));
    outer.setAttribute("y1", String(line.y1));
    outer.setAttribute("x2", String(line.x2));
    outer.setAttribute("y2", String(line.y2));
    outer.setAttribute("stroke", outerStroke);
    outer.setAttribute("stroke-width", "8");
    outer.setAttribute("stroke-linecap", "round");
    outer.setAttribute("opacity", "0.9");

    if (dash) {
        outer.setAttribute("stroke-dasharray", dash);
    }

    const inner = createSvgElement("line");

    inner.setAttribute("x1", String(line.x1));
    inner.setAttribute("y1", String(line.y1));
    inner.setAttribute("x2", String(line.x2));
    inner.setAttribute("y2", String(line.y2));
    inner.setAttribute("stroke", innerStroke);
    inner.setAttribute("stroke-width", "4");
    inner.setAttribute("stroke-linecap", "round");
    inner.setAttribute(
        "marker-end",
        `url(#${markerId})`
    );

    if (dash) {
        inner.setAttribute("stroke-dasharray", dash);
    }

    layer.appendChild(outer);
    layer.appendChild(inner);
}

function drawHold(layer, position, color = "#111827") {
    const ring = createSvgElement("circle");

    ring.setAttribute("cx", String(position.x));
    ring.setAttribute("cy", String(position.y));
    ring.setAttribute("r", "31");
    ring.setAttribute("fill", "none");
    ring.setAttribute("stroke", color);
    ring.setAttribute("stroke-width", "5");

    layer.appendChild(ring);
}

function GameMap({
    focusMode = false,
    phaseType = "movement",
    buildableCenters = [],
    units = [],
    myUnits = [],
    orders = [],
    historicalOrders = [],
    showHistoricalOrders = false,
    ordersLocked = false,
    supplyCenters = [],

    selectedUnit = null,
    supportedUnit = null,
    convoyedUnit = null,
    selectedTarget = "",
    draftOrderType = null,

    coastSelection = null,

    onSelectUnit,
    onProvinceClick,
    onOrderTypeSelect,
    onBuildTypeSelect,
    onSupportModeSelect,
    onCoastSelect,
}) {
    const containerRef = useRef(null);

    const [svgMarkup, setSvgMarkup] = useState("");
    // Presentation-only renders must not replace the imperative SVG subtree.
    const svgContent = useMemo(() => ({ __html: svgMarkup }), [svgMarkup]);
    const [unitPositions, setUnitPositions] = useState({});
    const [loadError, setLoadError] = useState("");

    const myUnitIds = useMemo(
        () => new Set(myUnits.map((unit) => unit.id)),
        [myUnits]
    );

    // Province clicks refer to the occupant. Dislodged markers select their
    // exact unit through their own listener, even when sharing a province.
    const activeUnitByProvince = useMemo(() => {
        const result = new Map();

        for (const unit of units) {
            if (unit.province_code && !unit.is_dislodged) {
                result.set(
                    unit.province_code.toUpperCase(),
                    unit
                );
            }
        }

        return result;
    }, [units]);

    const ordersByUnitId = useMemo(() => {
        const result = new Map();

        for (const order of orders) {
            if (order.saved_unit_id != null) {
                result.set(
                    Number(order.saved_unit_id),
                    order
                );
            }
        }

        return result;
    }, [orders]);



    useEffect(() => {
        let cancelled = false;

        async function loadSvg() {
            try {
                setLoadError("");

                const response = await fetch(
                    "/maps/standard.svg"
                );

                if (!response.ok) {
                    throw new Error(
                        `Nepodařilo se načíst mapu (${response.status}).`
                    );
                }

                const text = await response.text();

                const parser = new DOMParser();

                const documentSvg = parser.parseFromString(
                    text,
                    "image/svg+xml"
                );

                const parseError =
                    documentSvg.querySelector(
                        "parsererror"
                    );

                if (parseError) {
                    throw new Error(
                        "Soubor standard.svg není platné SVG."
                    );
                }

                const root =
                    documentSvg.documentElement;

                root.removeAttribute("width");
                root.removeAttribute("height");

                root.removeAttribute("style");
                root.setAttribute("preserveAspectRatio", "xMidYMid meet");

                const positions = {};

                const allElements =
                    Array.from(
                        documentSvg.getElementsByTagName("*")
                    );

                for (const element of allElements) {
                    if (
                        element.localName !== "PROVINCE"
                    ) {
                        continue;
                    }

                    const sourceProvinceName =
                        element
                            .getAttribute("name")
                            ?.toUpperCase();

                    if (!sourceProvinceName) {
                        continue;
                    }

                    const normalizedProvinceName =
                        normalizeSvgProvinceId(
                            sourceProvinceName
                        );

                    if (!normalizedProvinceName) {
                        continue;
                    }

                    const unitElement =
                        Array.from(
                            element.children
                        ).find(
                            (child) =>
                                child.localName === "UNIT"
                        );

                    if (!unitElement) {
                        continue;
                    }

                    const x = Number(
                        unitElement.getAttribute("x")
                    );

                    const y = Number(
                        unitElement.getAttribute("y")
                    );

                    if (
                        !Number.isFinite(x) ||
                        !Number.isFinite(y)
                    ) {
                        continue;
                    }

                    const sourceIsCanonical =
                        sourceProvinceName ===
                        normalizedProvinceName;

                    if (
                        !positions[
                            normalizedProvinceName
                        ] ||
                        sourceIsCanonical
                    ) {
                        positions[
                            normalizedProvinceName
                        ] = { x, y };
                    }
                }

                const serializer =
                    new XMLSerializer();

                const serialized =
                    serializer.serializeToString(
                        root
                    );

                if (!cancelled) {
                    setUnitPositions(positions);
                    setSvgMarkup(serialized);
                }

            } catch (error) {
                console.error(error);

                if (!cancelled) {
                    setLoadError(
                        error.message ||
                        "Mapu se nepodařilo načíst."
                    );
                }
            }
        }

        loadSvg();

        return () => {
            cancelled = true;
        };
    }, []);




    useEffect(() => {
        const container =
            containerRef.current;

        if (!container || !svgMarkup) {
            return;
        }

        const svg =
            container.querySelector("svg");

        if (!svg) {
            return;
        }

        for (const center of supplyCenters) {
            const provinceCode =
                center.province_code?.toUpperCase();

            if (!provinceCode) {
                continue;
            }

            const province =
                getVisibleProvinceElement(
                    svg,
                    provinceCode
                );

            if (!province) {
                continue;
            }

            const owner =
                center.owner_country;

            province.style.fill =
                owner
                    ? (
                        SUPPLY_CENTER_COLORS[owner] ??
                        "#dddddd"
                    )
                    : NEUTRAL_SUPPLY_CENTER_COLOR;
        }


        const oldUiLayer =
            svg.querySelector("#ReactUiLayer");

        if (oldUiLayer) {
            oldUiLayer.remove();
        }

        const uiLayer =
            createSvgElement("g");

        uiLayer.setAttribute(
            "id",
            "ReactUiLayer"
        );

        svg.appendChild(uiLayer);

        const defs =
            createSvgElement("defs");

        uiLayer.appendChild(defs);

        addArrowMarker(
            defs,
            "move-arrow",
            "#111827"
        );

        addArrowMarker(
            defs,
            "support-arrow",
            "#111827"
        );

        addArrowMarker(
            defs,
            "convoy-arrow",
            "#111827"
        );

        addArrowMarker(defs, "failed-arrow", "#dc2626");

        const orderLayer =
            createSvgElement("g");

        orderLayer.setAttribute(
            "id",
            "ReactOrderLayer"
        );

        orderLayer.setAttribute(
            "pointer-events",
            "none"
        );

        uiLayer.appendChild(orderLayer);

        const positionForUnit = (unit) => {
            const position = unitPositions[unit?.province_code?.toUpperCase()];
            return position && (phaseType === "retreat" || showHistoricalOrders) && unit.is_dislodged
                // Separate both markers, their selection rings and the R/D wheel.
                ? { x: position.x + 64, y: position.y + 40 }
                : position;
        };

        /*
         * Draw saved orders first so unit markers and the wheel remain
         * visually above them.
         */
        for (const order of (showHistoricalOrders ? historicalOrders : orders)) {
            const failed = showHistoricalOrders && order.result === "failed";
            const color = failed ? "#dc2626" : "#111827";
            const originCode =
                order.origin?.toUpperCase();

            const origin = !showHistoricalOrders && order.order_type === "retreat"
                ? positionForUnit(units.find((unit) => unit.id === order.saved_unit_id))
                : unitPositions[originCode];

            if (!origin) {
                continue;
            }

            if (order.order_type === "hold") {
                drawHold(
                    orderLayer,
                    origin,
                    color
                );

                continue;
            }

            if (order.order_type === "move" || order.order_type === "retreat") {
                const targetCode =
                    order.target_code
                        ?.toUpperCase();

                const target =
                    unitPositions[targetCode];

                if (!target) {
                    continue;
                }

                drawArrow(
                    orderLayer,
                    origin,
                    target,
                    {
                        markerId: failed ? "failed-arrow" : order.via_convoy ? "convoy-arrow" : "move-arrow",
                        innerStroke: color,
                        dash: order.via_convoy ? "14 6 3 6" : "",
                    }
                );

                continue;
            }

            if (order.order_type === "support") {
                const targetCode = (
                    order.support_target_code ||
                    order.supported_origin
                )?.toUpperCase();

                const target =
                    unitPositions[targetCode];

                if (!target) {
                    continue;
                }

                drawArrow(
                    orderLayer,
                    origin,
                    target,
                    {
                        dash: "3 8",
                        markerId: failed ? "failed-arrow" : "support-arrow",
                        innerStroke: color,
                    }
                );

                continue;
            }

            if (order.order_type === "convoy") {
                const targetCode = order.convoy_target_code?.toUpperCase();

                const target =
                    unitPositions[targetCode];

                if (!target) {
                    continue;
                }

                drawArrow(
                    orderLayer,
                    origin,
                    target,
                    {
                        dash: "14 6 3 6",
                        markerId: failed ? "failed-arrow" : "convoy-arrow",
                        innerStroke: color,
                    }
                );
            }
        }

        const unitLayer =
            createSvgElement("g");

        unitLayer.setAttribute(
            "id",
            "ReactUnitLayer"
        );

        unitLayer.setAttribute(
            "pointer-events",
            "none"
        );

        uiLayer.appendChild(unitLayer);

        for (const unit of units) {
            const provinceCode =
                unit.province_code
                    ?.toUpperCase();

            const position = positionForUnit(unit);

            if (
                !provinceCode ||
                !position
            ) {
                continue;
            }

            const hasSavedOrder =
                !showHistoricalOrders && ordersByUnitId.has(
                    Number(unit.id)
                );

            const group =
                createSvgElement("g");

            group.setAttribute(
                "transform",
                `translate(${position.x} ${position.y})`
            );

            const circle =
                createSvgElement("circle");

            circle.setAttribute(
                "cx",
                "0"
            );

            circle.setAttribute(
                "cy",
                "0"
            );

            circle.setAttribute(
                "r",
                "22"
            );

            circle.setAttribute(
                "fill",
                COUNTRY_COLORS[
                    unit.country
                ] || "#333333"
            );

            /*
             * White border + slight brightening = a valid saved order.
             * This is deliberately separate from selection.
             */
            if (hasSavedOrder) {
                circle.setAttribute(
                    "stroke",
                    "#ffffff"
                );

                circle.setAttribute(
                    "stroke-width",
                    "5"
                );

                circle.style.filter =
                    "brightness(1.14)";
            } else {
                circle.setAttribute(
                    "stroke",
                    "#111111"
                );

                circle.setAttribute(
                    "stroke-width",
                    "3"
                );
            }

            group.appendChild(circle);

            if ((phaseType === "retreat" || showHistoricalOrders) && unit.is_dislodged) {
                circle.setAttribute("stroke-dasharray", "5 4");
                const title = createSvgElement("title");
                title.textContent = "Vytlačená jednotka — vyžaduje ústup nebo rozpuštění";
                group.appendChild(title);
            }

            if (phaseType === "retreat" && !showHistoricalOrders && !ordersLocked) {
                const canSelect = unit.is_dislodged && myUnitIds.has(unit.id);
                // Override the unit layer's pointer-events="none". All markers
                // consume clicks so an occupant cannot select a defender beneath it.
                group.setAttribute("pointer-events", "all");
                group.style.cursor = canSelect || draftOrderType ? "pointer" : "default";
                group.addEventListener("click", (event) => {
                    event.stopPropagation();
                    if (draftOrderType) {
                        onProvinceClick?.(provinceCode, unit);
                    } else if (canSelect) {
                        onSelectUnit?.(unit);
                    }
                });
            }

            if (
                !showHistoricalOrders && (selectedUnit?.id === unit.id || convoyedUnit?.id === unit.id)
            ) {
                const selectionRing =
                    createSvgElement(
                        "circle"
                    );

                selectionRing.setAttribute(
                    "cx",
                    "0"
                );

                selectionRing.setAttribute(
                    "cy",
                    "0"
                );

                selectionRing.setAttribute(
                    "r",
                    "29"
                );

                selectionRing.setAttribute(
                    "fill",
                    "none"
                );

                selectionRing.setAttribute(
                    "stroke",
                    convoyedUnit?.id === unit.id ? "#06b6d4" : "#f59e0b"
                );

                selectionRing.setAttribute(
                    "stroke-width",
                    "5"
                );

                group.appendChild(
                    selectionRing
                );
            }

            const text =
                createSvgElement("text");

            text.setAttribute(
                "x",
                "0"
            );

            text.setAttribute(
                "y",
                "7"
            );

            text.setAttribute(
                "text-anchor",
                "middle"
            );

            text.setAttribute(
                "font-size",
                "23"
            );

            text.setAttribute(
                "font-weight",
                "700"
            );

            text.setAttribute(
                "fill",
                "#ffffff"
            );

            text.setAttribute(
                "font-family",
                "Arial, sans-serif"
            );

            text.textContent =
                unit.unit_type === "army"
                    ? "A"
                    : "F";

            group.appendChild(text);
            unitLayer.appendChild(group);
        }

        /*
         * Radial actions for a selected own unit or an authorized build center.
         *
         * Coastal Army: H / M / S / V
         * Fleet: H / M / S / C
         *
         * Convoy eligibility comes from the unit's province metadata.
         */
        const buildCenter = phaseType === "adjustment"
            ? buildableCenters.find((center) => center.code === selectedTarget)
            : null;
        if (
            !showHistoricalOrders && !ordersLocked && ((buildCenter && coastSelection?.mode !== "build") ||
            (selectedUnit &&
            (phaseType !== "retreat" || selectedUnit.is_dislodged) &&
            myUnitIds.has(
                selectedUnit.id
            )))
        ) {
            const selectedPosition = buildCenter
                ? unitPositions[buildCenter.code]
                : positionForUnit(selectedUnit);

            if (selectedPosition) {
                const wheel =
                    createSvgElement("g");

                wheel.setAttribute(
                    "id",
                    buildCenter ? "ReactBuildWheel" : "ReactOrderWheel"
                );

                wheel.setAttribute(
                    "transform",
                    `translate(${selectedPosition.x} ${selectedPosition.y})`
                );

                wheel.setAttribute(
                    "pointer-events",
                    "all"
                );

                uiLayer.appendChild(
                    wheel
                );

                const isFleet =
                    selectedUnit?.unit_type ===
                    "fleet";

                const options = buildCenter
                    ? [
                        ...(buildCenter.army_allowed
                            ? [{ type: "army", label: "A", title: "BUILD – Armáda", angle: 180 }]
                            : []),
                        ...(buildCenter.fleet_allowed
                            ? [{ type: "fleet", label: "F", title: "BUILD – Flotila", angle: 0 }]
                            : []),
                    ]
                    : phaseType === "retreat"
                    ? [
                        { type: "retreat", label: "R", title: "RETREAT – ústup", angle: -90 },
                        { type: "disband", label: "D", title: "DISBAND – rozpuštění", angle: 90 },
                    ]
                    : phaseType === "adjustment"
                    ? [{ type: "disband", label: "D", title: "DISBAND – rozpuštění", angle: -90 }]
                    : isFleet
                    ? [
                        {
                            type: "hold",
                            label: "H",
                            title: "HOLD",
                            angle: -90,
                        },
                        {
                            type: "move",
                            label: "M",
                            title: "MOVE",
                            angle: 0,
                        },
                        {
                            type: "support",
                            label: "S",
                            title: "SUPPORT",
                            angle: 90,
                        },
                        {
                            type: "convoy",
                            label: "C",
                            title: "CONVOY – přeprava armády",
                            angle: 180,
                            disabled: phaseType !== "movement" || selectedUnit.province_type !== "sea",
                        },
                    ]
                    : [
                        {
                            type: "hold",
                            label: "H",
                            title: "HOLD",
                            angle: -90,
                        },
                        {
                            type: "move",
                            label: "M",
                            title: "MOVE",
                            angle: selectedUnit.province_type === "coastal" ? 0 : 30,
                        },
                        {
                            type: "support",
                            label: "S",
                            title: "SUPPORT",
                            angle: selectedUnit.province_type === "coastal" ? 90 : 150,
                        },
                        ...(phaseType === "movement" && selectedUnit.province_type === "coastal"
                            ? [{ type: "move-convoy", label: "V", title: "MOVE VIA CONVOY", angle: 180 }]
                            : []),
                    ];

                const orbitRadius = 60;

                for (const option of options) {
                    const radians =
                        option.angle *
                        Math.PI /
                        180;

                    const cx =
                        Math.cos(radians) *
                        orbitRadius;

                    const cy =
                        Math.sin(radians) *
                        orbitRadius;

                    const button =
                        createSvgElement("g");

                    button.setAttribute(
                        "transform",
                        `translate(${cx} ${cy})`
                    );

                    button.setAttribute(
                        "pointer-events",
                        "all"
                    );

                    button.style.cursor =
                        option.disabled
                            ? "not-allowed"
                            : "pointer";

                    const active =
                        draftOrderType ===
                            option.type ||
                        (option.type === "convoy" && draftOrderType?.startsWith("convoy-")) ||
                        (
                            option.type ===
                                "support" &&
                            draftOrderType
                                ?.startsWith(
                                    "support"
                                )
                        );

                    const buttonCircle =
                        createSvgElement(
                            "circle"
                        );

                    buttonCircle.setAttribute(
                        "cx",
                        "0"
                    );

                    buttonCircle.setAttribute(
                        "cy",
                        "0"
                    );

                    buttonCircle.setAttribute(
                        "r",
                        "23"
                    );

                    buttonCircle.setAttribute(
                        "fill",
                        option.disabled
                            ? "#9ca3af"
                            : active
                                ? "#f59e0b"
                                : "#ffffff"
                    );

                    buttonCircle.setAttribute(
                        "stroke",
                        "#111827"
                    );

                    buttonCircle.setAttribute(
                        "stroke-width",
                        active
                            ? "5"
                            : "3"
                    );

                    const label =
                        createSvgElement(
                            "text"
                        );

                    label.setAttribute(
                        "x",
                        "0"
                    );

                    label.setAttribute(
                        "y",
                        "7"
                    );

                    label.setAttribute(
                        "text-anchor",
                        "middle"
                    );

                    label.setAttribute(
                        "font-size",
                        "20"
                    );

                    label.setAttribute(
                        "font-weight",
                        "800"
                    );

                    label.setAttribute(
                        "fill",
                        option.disabled
                            ? "#4b5563"
                            : "#111827"
                    );

                    label.setAttribute(
                        "pointer-events",
                        "none"
                    );

                    label.textContent =
                        option.label;

                    const title =
                        createSvgElement(
                            "title"
                        );

                    title.textContent =
                        option.title;

                    button.appendChild(
                        title
                    );

                    button.appendChild(
                        buttonCircle
                    );

                    button.appendChild(
                        label
                    );

                    if (!option.disabled) {
                        button.addEventListener(
                            "click",
                            (event) => {
                                event.stopPropagation();

                                if (buildCenter) {
                                    onBuildTypeSelect?.(option.type);
                                } else {
                                    onOrderTypeSelect?.(option.type);
                                }
                            }
                        );
                    }

                    wheel.appendChild(
                        button
                    );
                }
            }
        }






if (
    !showHistoricalOrders && !ordersLocked && draftOrderType === "support-mode" &&
    supportedUnit
) {
    const position =
        unitPositions[
            supportedUnit
                .province_code
                ?.toUpperCase()
        ];

    if (position) {
        const supportWheel =
            createSvgElement("g");

        supportWheel.setAttribute(
            "id",
            "ReactSupportModeWheel"
        );

        supportWheel.setAttribute(
            "transform",
            `translate(${position.x} ${position.y})`
        );

        supportWheel.setAttribute(
            "pointer-events",
            "all"
        );

        uiLayer.appendChild(
            supportWheel
        );

        const options = [
            {
                mode: "hold",
                label: "H",
                title: "SUPPORT HOLD",
                x: -48,
                y: -48,
            },
            {
                mode: "move",
                label: "M",
                title: "SUPPORT MOVE",
                x: 48,
                y: -48,
            },
        ];

        for (const option of options) {
            const button =
                createSvgElement("g");

            button.setAttribute(
                "transform",
                `translate(${option.x} ${option.y})`
            );

            button.style.cursor =
                "pointer";

            button.setAttribute(
                "pointer-events",
                "all"
            );

            const circle =
                createSvgElement("circle");

            circle.setAttribute(
                "r",
                "22"
            );

            circle.setAttribute(
                "fill",
                "#ffffff"
            );

            circle.setAttribute(
                "stroke",
                "#2563eb"
            );

            circle.setAttribute(
                "stroke-width",
                "4"
            );

            const text =
                createSvgElement("text");

            text.setAttribute(
                "x",
                "0"
            );

            text.setAttribute(
                "y",
                "7"
            );

            text.setAttribute(
                "text-anchor",
                "middle"
            );

            text.setAttribute(
                "font-size",
                "19"
            );

            text.setAttribute(
                "font-weight",
                "800"
            );

            text.setAttribute(
                "fill",
                "#111827"
            );

            text.setAttribute(
                "pointer-events",
                "none"
            );

            text.textContent =
                option.label;

            const title =
                createSvgElement("title");

            title.textContent =
                option.title;

            button.appendChild(title);
            button.appendChild(circle);
            button.appendChild(text);

            button.addEventListener(
                "click",
                (event) => {
                    event.stopPropagation();

                    onSupportModeSelect?.(
                        option.mode
                    );
                }
            );

            supportWheel.appendChild(
                button
            );
        }
    }
}


if (coastSelection && !showHistoricalOrders && !ordersLocked) {
    const position =
        unitPositions[
            coastSelection
                .provinceCode
                ?.toUpperCase()
        ];

    if (position) {
        const coastWheel =
            createSvgElement("g");

        coastWheel.setAttribute(
            "id",
            "ReactCoastSelector"
        );

        coastWheel.setAttribute(
            "transform",
            `translate(${position.x} ${position.y})`
        );

        coastWheel.setAttribute(
            "pointer-events",
            "all"
        );

        uiLayer.appendChild(
            coastWheel
        );

        const options =
            coastSelection.options;

        const spacing = 52;

        options.forEach(
            (coastCode, index) => {
                const offset =
                    (
                        index -
                        (options.length - 1) / 2
                    ) * spacing;

                const button =
                    createSvgElement("g");

                button.setAttribute(
                    "transform",
                    `translate(${offset} 52)`
                );

                button.setAttribute(
                    "pointer-events",
                    "all"
                );

                button.style.cursor =
                    "pointer";

                const circle =
                    createSvgElement("circle");

                circle.setAttribute(
                    "r",
                    "23"
                );

                circle.setAttribute(
                    "fill",
                    "#ffffff"
                );

                circle.setAttribute(
                    "stroke",
                    "#ef4444"
                );

                circle.setAttribute(
                    "stroke-width",
                    "4"
                );

                const text =
                    createSvgElement("text");

                text.setAttribute(
                    "x",
                    "0"
                );

                text.setAttribute(
                    "y",
                    "6"
                );

                text.setAttribute(
                    "text-anchor",
                    "middle"
                );

                text.setAttribute(
                    "font-size",
                    "15"
                );

                text.setAttribute(
                    "font-weight",
                    "800"
                );

                text.setAttribute(
                    "fill",
                    "#111827"
                );

                text.setAttribute(
                    "pointer-events",
                    "none"
                );

                text.textContent =
                    coastCode.toUpperCase();

                const title =
                    createSvgElement("title");

                title.textContent =
                    `Pobřeží ${coastCode.toUpperCase()}`;

                button.appendChild(
                    title
                );

                button.appendChild(
                    circle
                );

                button.appendChild(
                    text
                );

                button.addEventListener(
                    "click",
                    (event) => {
                        event.stopPropagation();

                        onCoastSelect?.(
                            coastCode
                        );
                    }
                );

                coastWheel.appendChild(
                    button
                );
            }
        );
    }
}


        // Visual target highlight.
        for (const code of PROVINCE_CODES) {
            const visibleProvince =
                getVisibleProvinceElement(
                    svg,
                    code
                );

            if (!visibleProvince) {
                continue;
            }

            visibleProvince.style.removeProperty(
                "stroke"
            );

            visibleProvince.style.removeProperty(
                "stroke-width"
            );

            visibleProvince.style.removeProperty(
                "filter"
            );
        }

        const highlightProvince = (
            code,
            stroke,
            strokeWidth,
            filter
        ) => {
            if (!code) {
                return;
            }

            const visibleProvince =
                getVisibleProvinceElement(
                    svg,
                    code
                );

            if (!visibleProvince) {
                return;
            }

            visibleProvince.style.stroke =
                stroke;

            visibleProvince.style.strokeWidth =
                strokeWidth;

            visibleProvince.style.filter =
                filter;
        };

        highlightProvince(
            showHistoricalOrders ? null : selectedUnit?.province_code,
            "#f59e0b",
            "7",
            "brightness(1.12)"
        );

        highlightProvince(
            showHistoricalOrders ? null : selectedTarget,
            "#ef4444",
            "7",
            "brightness(1.10)"
        );

        if (phaseType === "adjustment" && !showHistoricalOrders) {
            for (const center of buildableCenters) {
                if (center.code !== selectedTarget) {
                    highlightProvince(center.code, "#22c55e", "7", "brightness(1.12)");
                }
            }
        }

        const mouseLayer =
            svg.querySelector(
                "#MouseLayer"
            );

        let mouseLayerListener =
            null;

        if (mouseLayer) {
            const hitShapes =
                mouseLayer.querySelectorAll(
                    "path, polygon, rect, circle, ellipse, g"
                );

            for (const shape of hitShapes) {
                shape.style.pointerEvents =
                    "all";

                shape.style.cursor =
                    showHistoricalOrders || ordersLocked ? "default" : "pointer";
            }

            mouseLayer.style.pointerEvents =
                "all";

            mouseLayerListener = (
                event
            ) => {
                if (showHistoricalOrders || ordersLocked) return;
                let current =
                    event.target;

                while (
                    current &&
                    current !== mouseLayer
                ) {
                    const provinceCode =
                        normalizeSvgProvinceId(
                            current.id
                        );

                    if (provinceCode) {
                        const unit =
                            activeUnitByProvince.get(
                                provinceCode
                            ) ?? null;

                        if (phaseType === "adjustment") {
                            if (unit && myUnitIds.has(unit.id) && !unit.is_dislodged) {
                                onSelectUnit?.(unit);
                            } else if (buildableCenters.some((center) => center.code === provinceCode)) {
                                onProvinceClick?.(provinceCode, unit);
                            }
                            return;
                        }

                        /*
                         * When an order type is already selected, every map
                         * click is part of that order. Otherwise, clicking an
                         * own unit selects it and opens the radial wheel.
                         */
                        if (
                            draftOrderType
                        ) {
                            onProvinceClick?.(
                                provinceCode,
                                unit
                            );

                            return;
                        }

                        // In Retreat only the exact owned dislodged marker (or
                        // the page's unit list) selects a unit, never the province.
                        if (phaseType === "retreat") {
                            return;
                        }

                        if (
                            unit &&
                            myUnitIds.has(
                                unit.id
                            )
                        ) {
                            onSelectUnit?.(
                                unit
                            );

                            return;
                        }

                        if (selectedUnit) {
                            onProvinceClick?.(
                                provinceCode,
                                unit
                            );

                            return;
                        }

                        return;
                    }

                    current =
                        current.parentElement;
                }
            };

            mouseLayer.addEventListener(
                "click",
                mouseLayerListener
            );
        }

        return () => {
            if (
                mouseLayer &&
                mouseLayerListener
            ) {
                mouseLayer.removeEventListener(
                    "click",
                    mouseLayerListener
                );
            }

            uiLayer.remove();
        };
    }, [
        phaseType,
        historicalOrders,
        showHistoricalOrders,
        ordersLocked,
        buildableCenters,
        svgMarkup,
        unitPositions,
        units,
        supplyCenters,
        supportedUnit,
        convoyedUnit,
        onSupportModeSelect,
        activeUnitByProvince,
        myUnitIds,
        orders,
        coastSelection,
        onCoastSelect,
        ordersByUnitId,
        selectedUnit,
        selectedTarget,
        draftOrderType,
        onSelectUnit,
        onProvinceClick,
        onOrderTypeSelect,
        onBuildTypeSelect,
    ]);

    if (loadError) {
        return (
            <section className={`game-map${focusMode ? " game-map--focus" : ""}`}>
                {!focusMode && <h3>Mapa</h3>}

                <p>{loadError}</p>

                <p>
                    Zkontroluj, že existuje soubor:{" "}
                    <code>
                        frontend/public/maps/standard.svg
                    </code>
                </p>
            </section>
        );
    }

    return (
        <section className={`game-map${focusMode ? " game-map--focus" : ""}`}>
            {!focusMode && <h3>Mapa</h3>}

            {!svgMarkup && (
                <p>Načítání mapy...</p>
            )}

            <div
                ref={containerRef}
                className="game-map-canvas"
                dangerouslySetInnerHTML={svgContent}
            >
            </div>
        </section>
    );
}

export default GameMap;
