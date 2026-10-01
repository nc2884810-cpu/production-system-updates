"use strict";

const byId = (id) => document.getElementById(id);

const productionRecords = [];

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
    defectReason: byId("defectReason"),
    totalProduced: byId("totalProduced"),
    totalGood: byId("totalGood"),
    totalDefect: byId("totalDefect"),
    totalDefectPercent: byId("totalDefectPercent"),
    emptyMessage: byId("emptyMessage"),
    tableWrapper: byId("productionTableWrapper"),
    tableBody: byId("productionTableBody"),
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
    renderStatistics();
    renderProductionTable();
    bindEvents();
}

function bindEvents() {
    ui.addButton.addEventListener("click", openModal);
    ui.closeButton.addEventListener("click", closeModal);
    ui.cancelButton.addEventListener("click", closeModal);
    ui.form.addEventListener("submit", addProductionRecord);

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

function addProductionRecord(event) {
    event.preventDefault();

    const record = readFormRecord();
    const validationError = validateRecord(record);

    if (validationError) {
        setMessage(validationError, "error");
        return;
    }

    productionRecords.unshift(record);
    renderProductionTable();
    renderStatistics();
    closeModal();
}

function readFormRecord() {
    const quantity = Number(ui.quantity.value);
    const goodQuantity = Number(ui.goodQuantity.value);
    const defectQuantity = Number(ui.defectQuantity.value);

    return {
        date: new Date(),
        productName: ui.productName.value.trim(),
        quantity,
        goodQuantity,
        defectQuantity,
        defectPercent: quantity > 0 ? (defectQuantity / quantity) * 100 : 0,
        defectReason: ui.defectReason.value.trim(),
    };
}

function validateRecord(record) {
    if (!record.productName) {
        return "Укажите изделие.";
    }

    if (!Number.isFinite(record.quantity) || record.quantity <= 0) {
        return "Общее количество должно быть больше нуля.";
    }

    if (
        !Number.isFinite(record.goodQuantity) ||
        !Number.isFinite(record.defectQuantity) ||
        record.goodQuantity < 0 ||
        record.defectQuantity < 0
    ) {
        return "Количество годных изделий и брака не может быть отрицательным.";
    }

    if (record.goodQuantity + record.defectQuantity !== record.quantity) {
        return "Ошибка: годных + брак должны быть равны общему количеству.";
    }

    return "";
}

function renderProductionTable() {
    const hasRecords = productionRecords.length > 0;

    ui.emptyMessage.hidden = hasRecords;
    ui.tableWrapper.hidden = !hasRecords;
    ui.tableBody.replaceChildren();

    const fragment = document.createDocumentFragment();

    for (const record of productionRecords) {
        const row = document.createElement("tr");

        appendCell(row, formatDate(record.date));
        appendCell(row, record.productName);
        appendCell(row, record.quantity, "numeric");
        appendCell(row, record.goodQuantity, "numeric");
        appendCell(row, record.defectQuantity, "numeric");
        appendCell(row, `${record.defectPercent.toFixed(2)}%`, "numeric");
        appendCell(row, record.defectReason || "—", "reason-cell");

        fragment.appendChild(row);
    }

    ui.tableBody.appendChild(fragment);
}

function appendCell(row, value, className = "") {
    const cell = document.createElement("td");
    cell.textContent = String(value);

    if (className) {
        cell.className = className;
    }

    row.appendChild(cell);
}

function renderStatistics() {
    const totals = productionRecords.reduce(
        (result, record) => {
            result.quantity += record.quantity;
            result.good += record.goodQuantity;
            result.defect += record.defectQuantity;
            return result;
        },
        { quantity: 0, good: 0, defect: 0 }
    );

    const defectPercent =
        totals.quantity > 0 ? (totals.defect / totals.quantity) * 100 : 0;

    ui.totalProduced.textContent = totals.quantity;
    ui.totalGood.textContent = totals.good;
    ui.totalDefect.textContent = totals.defect;
    ui.totalDefectPercent.textContent = `${defectPercent.toFixed(2)}%`;
}

function formatDate(date) {
    return new Intl.DateTimeFormat("ru-RU").format(date);
}
