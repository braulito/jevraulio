"use strict";

function mostrarRespuestaMarkdown(contenido, texto) {
    if (!window.marked || !window.DOMPurify) {
        contenido.textContent = texto;
        return;
    }
    try {
        const html = window.marked.parse(texto, { gfm: true, breaks: true });
        const fragmento = window.DOMPurify.sanitize(html, {
            USE_PROFILES: { html: true },
            FORBID_TAGS: ["style", "form", "input", "button", "textarea"],
            RETURN_DOM_FRAGMENT: true,
        });
        contenido.replaceChildren(fragmento);
        contenido.classList.add("mensaje-markdown");
    } catch {
        contenido.textContent = texto;
    }
}
