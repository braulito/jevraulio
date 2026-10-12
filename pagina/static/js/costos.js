"use strict";

const filtrosCostos = document.getElementById("filtros-costos");
if (filtrosCostos) {
    filtrosCostos.addEventListener("change", () => filtrosCostos.requestSubmit());
}
