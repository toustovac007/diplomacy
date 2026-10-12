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

/*
 * The source jDip SVG uses a few historical/internal IDs that differ from
 * the province codes used by our backend.
 *
 * Backend -> SVG:
 * MAO -> mid
 * NAO -> nat
 * NWG -> nrg
 * TYS -> tyn
 *
 * We keep both spellings where possible so this component also works with
 * slightly different versions of the SVG.
 */
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

    // First resolve exact aliases used by the SVG.
    if (SVG_ID_TO_GAME_CODE[normalized]) {
        return SVG_ID_TO_GAME_CODE[normalized];
    }

    // Coast-specific mouse zones such as spa-nc, spa-sc, stp-nc,
    // stp-sc, bul-ec and bul-sc still belong to one game province.
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

function GameMap({
    units = [],
    myUnits = [],
    selectedUnit = null,
    selectedTarget = "",
    onSelectUnit,
    onProvinceClick,
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

    // Load the full standard-map SVG from /public/maps/standard.svg.
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

                // Make the SVG responsive.
                root.removeAttribute("width");
                root.removeAttribute("height");

                root.setAttribute(
                    "style",
                    "width:100%;height:auto;display:block;"
                );

                // Read unit anchor points embedded in the map metadata.
                // Some metadata entries use the same historical aliases
                // as the SVG mouse layer, so normalize them as well.
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

                    /*
                     * Prefer metadata whose source name is already the same
                     * code as our backend. If only an alias exists (e.g. MID
                     * for MAO), use the alias position.
                     */
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

    // Add click handling, highlights and unit markers after SVG is inserted.
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

        const mouseLayer =
            svg.querySelector("#MouseLayer");

        const handleProvinceClick = (
            provinceCode
        ) => {
            const unit =
                unitsByProvince.get(
                    provinceCode
                );

            if (
                unit &&
                myUnitIds.has(unit.id)
            ) {
                onSelectUnit?.(unit);
                return;
            }

            if (selectedUnit) {
                onProvinceClick?.(
                    provinceCode
                );
            }
        };

        /*
         * IMPORTANT:
         *
         * Do not attach handlers only to "#MouseLayer #PAR", etc.
         *
         * The source SVG contains:
         * - historical sea IDs: mid/nat/nrg/tyn
         * - separate coast overlays: spa-nc, spa-sc, stp-nc, ...
         *
         * Those coast overlays can sit above the generic province path and
         * intercept the mouse. Event delegation on the complete MouseLayer
         * lets us map every one of those shapes back to a single backend
         * province code.
         */
        let mouseLayerListener = null;

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
                        handleProvinceClick(
                            provinceCode
                        );

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

        // Reset and apply visual highlighting.
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

        // Draw current units into the map's built-in UnitLayer.
        const unitLayer =
            svg.querySelector("#UnitLayer");

        if (unitLayer) {
            while (unitLayer.firstChild) {
                unitLayer.removeChild(
                    unitLayer.firstChild
                );
            }

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

                const group =
                    document.createElementNS(
                        SVG_NS,
                        "g"
                    );

                group.setAttribute(
                    "transform",
                    `translate(${position.x} ${position.y})`
                );

                group.setAttribute(
                    "pointer-events",
                    "none"
                );

                const circle =
                    document.createElementNS(
                        SVG_NS,
                        "circle"
                    );

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

                circle.setAttribute(
                    "stroke",
                    "#111111"
                );

                circle.setAttribute(
                    "stroke-width",
                    "3"
                );

                if (
                    selectedUnit?.id ===
                    unit.id
                ) {
                    circle.setAttribute(
                        "stroke",
                        "#f59e0b"
                    );

                    circle.setAttribute(
                        "stroke-width",
                        "7"
                    );
                }

                const text =
                    document.createElementNS(
                        SVG_NS,
                        "text"
                    );

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

                group.appendChild(circle);
                group.appendChild(text);

                unitLayer.appendChild(
                    group
                );
            }
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
        };
    }, [
        svgMarkup,
        unitPositions,
        units,
        unitsByProvince,
        myUnitIds,
        selectedUnit,
        selectedTarget,
        onSelectUnit,
        onProvinceClick,
    ]);

    if (loadError) {
        return (
            <div>
                <h3>Mapa</h3>

                <p>{loadError}</p>

                <p>
                    Zkontroluj, že existuje
                    soubor:{" "}
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
                    border:
                        "1px solid #aaa",
                    overflow: "hidden",
                    background: "#c5dfea",
                }}
                dangerouslySetInnerHTML={{
                    __html: svgMarkup,
                }}
            />
        </section>
    );
}

export default GameMap;
