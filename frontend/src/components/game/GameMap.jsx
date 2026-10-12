import { useEffect, useMemo, useRef, useState } from "react";

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

const COUNTRY_COLORS = {
    AUS: "#c48f85",
    ENG: "#8a2be2",
    FRA: "#4169e1",
    GER: "#a08a75",
    ITA: "#228b22",
    RUS: "#757d91",
    TUR: "#b9a61c",
};

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

function drawHold(layer, position) {
    const ring = createSvgElement("circle");

    ring.setAttribute("cx", String(position.x));
    ring.setAttribute("cy", String(position.y));
    ring.setAttribute("r", "31");
    ring.setAttribute("fill", "none");
    ring.setAttribute("stroke", "#111827");
    ring.setAttribute("stroke-width", "5");

    layer.appendChild(ring);
}

function GameMap({
    units = [],
    myUnits = [],
    orders = [],

    selectedUnit = null,
    selectedTarget = "",
    draftOrderType = null,

    onSelectUnit,
    onProvinceClick,
    onOrderTypeSelect,
}) {
    const containerRef = useRef(null);

    const [svgMarkup, setSvgMarkup] = useState("");
    const [unitPositions, setUnitPositions] = useState({});
    const [loadError, setLoadError] = useState("");

    const myUnitIds = useMemo(
        () => new Set(myUnits.map((unit) => unit.id)),
        [myUnits]
    );

    const unitsByProvince = useMemo(() => {
        const result = new Map();

        for (const unit of units) {
            if (unit.province_code) {
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

                root.setAttribute(
                    "style",
                    "width:100%;height:auto;display:block;"
                );

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
        setLoadError("");
        setUnitPositions({});
        setSvgMarkup("");
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

        /*
         * Draw saved orders first so unit markers and the wheel remain
         * visually above them.
         */
        for (const order of orders) {
            const originCode =
                order.origin?.toUpperCase();

            const origin =
                unitPositions[originCode];

            if (!origin) {
                continue;
            }

            if (order.order_type === "hold") {
                drawHold(
                    orderLayer,
                    origin
                );

                continue;
            }

            if (order.order_type === "move") {
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
                        markerId:
                            "move-arrow",
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
                        markerId:
                            "support-arrow",
                    }
                );

                continue;
            }

            /*
             * CONVOY is not implemented by the backend yet, but the renderer
             * is already prepared for it.
             */
            if (order.order_type === "convoy") {
                const targetCode = (
                    order.target_code ||
                    order.support_target_code
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
                        dash: "14 6 3 6",
                        markerId:
                            "convoy-arrow",
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

            const position =
                unitPositions[
                    provinceCode
                ];

            if (
                !provinceCode ||
                !position
            ) {
                continue;
            }

            const hasSavedOrder =
                ordersByUnitId.has(
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

            if (
                selectedUnit?.id ===
                unit.id
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
                    "#f59e0b"
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
         * Radial order wheel. Only appears for one selected own unit.
         *
         * Army: H / M / S
         * Fleet: H / M / S / C
         *
         * C is deliberately disabled until backend convoy adjudication exists.
         */
        if (
            selectedUnit &&
            myUnitIds.has(
                selectedUnit.id
            )
        ) {
            const selectedPosition =
                unitPositions[
                    selectedUnit
                        .province_code
                        ?.toUpperCase()
                ];

            if (selectedPosition) {
                const wheel =
                    createSvgElement("g");

                wheel.setAttribute(
                    "id",
                    "ReactOrderWheel"
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
                    selectedUnit.unit_type ===
                    "fleet";

                const options = isFleet
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
                            title: "CONVOY – zatím není implementovaný",
                            angle: 180,
                            disabled: true,
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
                            angle: 30,
                        },
                        {
                            type: "support",
                            label: "S",
                            title: "SUPPORT",
                            angle: 150,
                        },
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

                                onOrderTypeSelect?.(
                                    option.type
                                );
                            }
                        );
                    }

                    wheel.appendChild(
                        button
                    );
                }
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
            selectedUnit?.province_code,
            "#f59e0b",
            "7",
            "brightness(1.12)"
        );

        highlightProvince(
            selectedTarget,
            "#ef4444",
            "7",
            "brightness(1.10)"
        );

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
                    "pointer";
            }

            mouseLayer.style.pointerEvents =
                "all";

            mouseLayerListener = (
                event
            ) => {
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
                            unitsByProvince.get(
                                provinceCode
                            ) ?? null;

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
        svgMarkup,
        unitPositions,
        units,
        unitsByProvince,
        myUnitIds,
        orders,
        ordersByUnitId,
        selectedUnit,
        selectedTarget,
        draftOrderType,
        onSelectUnit,
        onProvinceClick,
        onOrderTypeSelect,
    ]);

    if (loadError) {
        return (
            <div>
                <h3>Mapa</h3>

                <p>{loadError}</p>

                <p>
                    Zkontroluj, že existuje soubor:{" "}
                    <code>
                        frontend/public/maps/standard.svg
                    </code>
                </p>
            </div>
        );
    }

    return (
        <section>
            <h3>Mapa</h3>

            {!svgMarkup && (
                <p>Načítání mapy...</p>
            )}

            <div
                ref={containerRef}
                style={{
                    width: "100%",
                    maxWidth: "1100px",
                    margin: "0 auto",
                    border: "1px solid #aaa",
                    overflow: "hidden",
                    background: "#c5dfea",
                }}
                dangerouslySetInnerHTML={{
                    __html: svgMarkup,
                }}
            >
            </div>
        </section>
    );
}

export default GameMap;
