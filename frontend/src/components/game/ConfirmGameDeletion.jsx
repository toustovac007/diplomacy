import { useEffect, useRef } from "react";

export default function ConfirmGameDeletion({ gameName, deleting, error, onCancel, onConfirm }) {
    const panel = useRef(null);
    const cancel = useRef(null);
    useEffect(() => {
        const previous = document.activeElement;
        const overflow = document.body.style.overflow;
        document.body.style.overflow = "hidden";
        cancel.current?.focus();
        return () => { document.body.style.overflow = overflow; if (previous?.isConnected) previous.focus(); };
    }, []);
    useEffect(() => { if (deleting) panel.current?.focus(); else cancel.current?.focus(); }, [deleting]);
    return <div className="lobby-confirm-backdrop" onClick={(event) => {
        if (event.target === event.currentTarget && !deleting) onCancel();
    }}>
        <section ref={panel} className="lobby-confirm" role="alertdialog" aria-modal="true"
            aria-labelledby="delete-game-title" aria-describedby="delete-game-description"
            aria-busy={deleting} tabIndex={-1} onKeyDown={(event) => {
                if (event.key === "Escape") { event.preventDefault(); if (!deleting) onCancel(); }
                if (event.key === "Tab") {
                    const buttons = [...panel.current.querySelectorAll("button:not(:disabled)")];
                    if (!buttons.length) { event.preventDefault(); return; }
                    const first = buttons[0], last = buttons.at(-1);
                    const outside = document.activeElement === panel.current || !panel.current.contains(document.activeElement);
                    if (event.shiftKey && (outside || document.activeElement === first)) { event.preventDefault(); last.focus(); }
                    else if (!event.shiftKey && (outside || document.activeElement === last)) { event.preventDefault(); first.focus(); }
                }
            }}>
            <h2 id="delete-game-title">Smazat čekající hru?</h2>
            <p id="delete-game-description">Hra „{gameName}“ bude trvale odstraněna. Všem připojeným hráčům se celá sázka vrátí mezi dostupné tokeny.</p>
            {error && <p role="alert">{error}</p>}
            <div className="lobby-confirm-actions">
                <button ref={cancel} type="button" disabled={deleting} onClick={onCancel}>Ponechat hru</button>
                <button type="button" disabled={deleting} onClick={onConfirm}>{deleting ? "Mažu…" : "Ano, smazat hru"}</button>
            </div>
        </section>
    </div>;
}
