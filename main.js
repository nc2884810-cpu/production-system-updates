"use strict";

const byId = (id) => document.getElementById(id);

const ui = {
    addButton: byId("addProductionButton"),
    modal: byId("productionModal"),
    closeButton: byId("closeModalButton"),
    cancelButton: byId("cancelButton"),
    form: byId("productionForm"),
    message: byId("formMessage"),
    currentDate: byId("currentDate"),
    version: byId("appVersion"),
    productName: byId("productName"),
    quantity: byId("quantity"),
    goodQuantity: byId("goodQuantity"),
    defectQuantity: byId("defectQuantity"),
};

const requiredElements = Object.values(ui);

if (requiredElements.some((element) => !element)) {
    console.error("Ошибка интерфейса: один или несколько обязательных элементов не найдены.");
} else {
    init();
}

function init() {
    renderDate();
    renderVersion();
    bindEvents();
}

function bindEvents() {
    ui.addButton.addEventListener("click", openModal);
    ui.closeButton.addEventListener("click", closeModal);
    ui.cancelButton.addEventListener("click", closeModal);
    ui.form.addEventListener("submit", validateProduction);

    ui.modal.addEventListener("click", (event) => {
        if (event.target === ui.modal) {
            closeModal();
        }
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && !ui.modal.classList.contains("hidden")) {
            closeModal();
        }
    });
}

function renderDate() {
    ui.currentDate.textContent =
        "Сегодня: " + new Intl.DateTimeFormat("ru-RU").format(new Date());
}

async function renderVersion() {
    try {
        const response = await fetch("version.txt", { cache: "no-store" });
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const version = (await response.text()).trim();
        ui.version.textContent = `Версия: ${version || "—"}`;
    } catch (error) {
        ui.version.textContent = "Версия: —";
        console.warn("Не удалось прочитать version.txt:", error);
    }
}

function openModal() {
    setModalVisibility(true);
    setMessage();
    ui.productName.focus();
}

function closeModal() {
    setModalVisibility(false);
    ui.form.reset();
    setMessage();
}

function setModalVisibility(isOpen) {
    ui.modal.classList.toggle("hidden", !isOpen);
    ui.modal.setAttribute("aria-hidden", String(!isOpen));
    document.body.classList.toggle("modal-open", isOpen);
}

function setMessage(text = "", type = "") {
    ui.message.textContent = text;
    ui.message.className = type ? `form-message ${type}` : "form-message";
}

function validateProduction(event) {
    event.preventDefault();

    const quantity = Number(ui.quantity.value);
    const goodQuantity = Number(ui.goodQuantity.value);
    const defectQuantity = Number(ui.defectQuantity.value);

    if (goodQuantity + defectQuantity !== quantity) {
        setMessage(
            "Ошибка: годных + брак должны быть равны общему количеству.",
            "error"
        );
        return;
    }

    const defectPercent = ((defectQuantity / quantity) * 100).toFixed(2);
    setMessage(`Проверка пройдена. Процент брака: ${defectPercent}%`, "success");
}
