"use strict";

const formulario = document.getElementById("formulario-chat");
const maxContexto = Number(formulario.dataset.maxContexto);
const pregunta = document.getElementById("pregunta");
const enviar = document.getElementById("enviar");
const estado = document.getElementById("estado-chat");
const conversacion = document.getElementById("conversacion");
const bienvenida = document.getElementById("bienvenida");
const ayuda = "Enter para enviar · Shift + Enter para una nueva línea";
// Contexto limitado a esta pestaña; se descarta al recargar la página.
const historial = [];

function irAlUltimoMensaje() {
    conversacion.scrollTop = conversacion.scrollHeight;
}

function agregarMensaje(tipo, texto) {
    const mensaje = document.createElement("article");
    mensaje.className = `mensaje mensaje-${tipo}`;
    mensaje.setAttribute("aria-label", tipo === "usuario" ? "Tu pregunta" : "Respuesta");
    const contenido = document.createElement("div");
    contenido.className = "mensaje-texto";
    contenido.textContent = texto;
    mensaje.append(contenido);
    conversacion.append(mensaje);
    return { mensaje, contenido };
}

function agregarCopiar(mensaje, texto) {
    const boton = document.createElement("button");
    boton.type = "button";
    boton.className = "copiar-respuesta";
    boton.setAttribute("aria-label", "Copiar respuesta");
    boton.title = "Copiar respuesta";
    // Ícono fijo; las respuestas se muestran con Markdown sanitizado.
    boton.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="8" y="8" width="12" height="12" rx="3"/><path d="M16 8V5a3 3 0 0 0-3-3H5a3 3 0 0 0-3 3v8a3 3 0 0 0 3 3h3"/></svg>';
    boton.addEventListener("click", async () => {
        try {
            await navigator.clipboard.writeText(texto);
            estado.textContent = "Respuesta copiada.";
        } catch {
            estado.textContent = "No se pudo copiar. Podés seleccionar el texto y copiarlo.";
        }
    });
    mensaje.append(boton);
}

formulario.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    if (enviar.disabled) return;
    const mensaje = pregunta.value.trim();
    if (!mensaje) {
        pregunta.setCustomValidity("Escribí una pregunta.");
        pregunta.reportValidity();
        return;
    }

    bienvenida.hidden = true;
    agregarMensaje("usuario", mensaje);
    const pendiente = agregarMensaje("asistente", "Esperando respuesta…");
    pendiente.mensaje.classList.add("mensaje-pendiente");
    enviar.disabled = true;
    pregunta.readOnly = true;
    pregunta.value = "";
    pregunta.style.height = "auto";
    estado.textContent = "Consultando, esperá un momento…";
    formulario.setAttribute("aria-busy", "true");
    irAlUltimoMensaje();

    let texto;
    try {
        const respuesta = await fetch(formulario.action, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ mensaje, contexto: historial.slice(-maxContexto) }),
        });
        if (respuesta.status !== 200) throw new Error("Error HTTP");
        const datos = await respuesta.json();
        if (typeof datos.respuesta !== "string") throw new Error("Respuesta inválida");
        texto = datos.respuesta;
        historial.push(`Usuario: ${mensaje}`.slice(0, 10000), `Asistente: ${texto}`.slice(0, 10000));
        historial.splice(0, Math.max(0, historial.length - maxContexto));
    } catch {
        texto = "Ocurrió un error.";
    } finally {
        mostrarRespuestaMarkdown(pendiente.contenido, texto);
        pendiente.mensaje.classList.remove("mensaje-pendiente");
        agregarCopiar(pendiente.mensaje, texto);
        enviar.disabled = false;
        pregunta.readOnly = false;
        estado.textContent = ayuda;
        formulario.setAttribute("aria-busy", "false");
        irAlUltimoMensaje();
        pregunta.focus({ preventScroll: true });
    }
});

pregunta.addEventListener("input", () => {
    pregunta.setCustomValidity("");
    pregunta.style.height = "auto";
    pregunta.style.height = `${Math.min(pregunta.scrollHeight, 160)}px`;
});

pregunta.addEventListener("keydown", (evento) => {
    if (evento.key === "Enter" && !evento.shiftKey && !evento.isComposing) {
        evento.preventDefault();
        if (!enviar.disabled) formulario.requestSubmit();
    }
});
