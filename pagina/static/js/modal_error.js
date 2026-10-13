"use strict";

const modalError = document.getElementById("modal-error");
if (modalError) {
    if (typeof modalError.showModal === "function") {
        modalError.showModal();
    } else {
        modalError.setAttribute("open", "");
    }
}
