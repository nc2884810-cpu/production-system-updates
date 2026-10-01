"use strict";

const byId = (id) => document.getElementById(id);

const productionRecords = [];
let editingRecordId = null;

const ui = {
    addButton: byId("addProductionButton"),
    modal: byId("productionModal"),
    modalTitle: byId("productionModalTitle"),
    closeButton: byId("closeModalButton"),
    cancelButton: byId("cancelButton"),
    submitButton: byId("submitProductionButton"),
    form: byId("productionForm"),
    message: byId("formMessage"),
    currentDate: byId("currentDate"),
    version: byId("appVersion"),
    storageStatus: byId("storageStatus"),
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

async function init() {
    renderDate();
    renderVersion();
    renderStatistics();
    renderProductionTable();
    bindEvents();
    await loadProductionRecords();
}

function bindEvents() {
    ui.addButton.addEventListener("click", openCreateModal);
    ui.closeButton.addEventListener("click", closeModal);
    ui.cancelButton.addEventListener("click", closeModal);
    ui.form.addEventListener("submit", saveProductionRecord);
    ui.tableBody.addEventListener("click", handleTableAction);

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

async function loadProductionRecords() {
    ui.storageStatus.textContent = "Загрузка сохранённых записей...";

    try {
        const data = await requestJson("/api/records");
        const records = Array.isArray(data.records) ? data.records : [];

        productionRecords.splice(
            0,
            productionRecords.length,
            ...records.map(normalizeRecord)
        );

        renderAll();
        updateStorageStatus();
    } catch (error) {
        ui.storageStatus.textContent =
            "Не удалось подключиться к хранилищу. Проверьте server.py.";
        console.error("Ошибка загрузки записей:", error);
    }
}

function openCreateModal() {
    editingRecordId = null;
    ui.form.reset();
    ui.modalTitle.textContent = "Добавить производство";
    setSubmitState(false);
    setMessage();
    setModalVisibility(true);
    ui.productName.focus();
}

function openEditModal(record) {
    editingRecordId = record.id;
    ui.productName.value = record.productName;
    ui.quantity.value = record.quantity;
    ui.goodQuantity.value = record.goodQuantity;
    ui.defectQuantity.value = record.defectQuantity;
    ui.defectReason.value = record.defectReason;
    ui.modalTitle.textContent = `Изменить запись №${record.id}`;
    setSubmitState(false);
    setMessage();
    setModalVisibility(true);
    ui.productName.focus();
}

function closeModal() {
    setModalVisibility(false);
    ui.form.reset();
    editingRecordId = null;
    ui.modalTitle.textContent = "Добавить производство";
    setMessage();
    setSubmitState(false);
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

function setSubmitState(isSaving) {
    ui.submitButton.disabled = isSaving;

    if (isSaving) {
        ui.submitButton.textContent = "Сохранение...";
        return;
    }

    ui.submitButton.textContent =
        editingRecordId === null ? "Добавить запись" : "Сохранить изменения";
}

async function saveProductionRecord(event) {
    event.preventDefault();

    const record = readFormRecord();
    const validationError = validateRecord(record);

    if (validationError) {
        setMessage(validationError, "error");
        return;
    }

    setSubmitState(true);
    setMessage("Сохраняю запись...");

    try {
        if (editingRecordId === null) {
            await createProductionRecord(record);
        } else {
            await updateProductionRecord(editingRecordId, record);
        }

        renderAll();
        updateStorageStatus();
        closeModal();
    } catch (error) {
        setMessage(
            error.message || "Не удалось сохранить запись на сервере.",
            "error"
        );
        setSubmitState(false);
        console.error("Ошибка сохранения записи:", error);
    }
}

async function createProductionRecord(record) {
    const data = await requestJson("/api/records", {
        method: "POST",
        headers: jsonHeaders(),
        body: JSON.stringify(record),
    });

    productionRecords.unshift(normalizeRecord(data.record));
}

async function updateProductionRecord(recordId, record) {
    const data = await requestJson(`/api/records/${recordId}`, {
        method: "PUT",
        headers: jsonHeaders(),
        body: JSON.stringify(record),
    });

    const index = productionRecords.findIndex(
        (item) => item.id === Number(recordId)
    );

    if (index === -1) {
        await loadProductionRecords();
        return;
    }

    productionRecords[index] = normalizeRecord(data.record);
}

async function deleteProductionRecord(record) {
    const confirmed = window.confirm(
        `Удалить запись №${record.id} «${record.productName}»?\n\nЭто действие нельзя отменить.`
    );

    if (!confirmed) {
        return;
    }

    try {
        await requestJson(`/api/records/${record.id}`, {
            method: "DELETE",
        });

        const index = productionRecords.findIndex(
            (item) => item.id === record.id
        );

        if (index !== -1) {
            productionRecords.splice(index, 1);
        }

        renderAll();
        updateStorageStatus();
    } catch (error) {
        window.alert(error.message || "Не удалось удалить запись.");
        console.error("Ошибка удаления записи:", error);
    }
}

function handleTableAction(event) {
    const button = event.target.closest("button[data-action]");

    if (!button) {
        return;
    }

    const recordId = Number(button.dataset.recordId);
    const record = productionRecords.find((item) => item.id === recordId);

    if (!record) {
        return;
    }

    if (button.dataset.action === "edit") {
        openEditModal(record);
        return;
    }

    if (button.dataset.action === "delete") {
        deleteProductionRecord(record);
    }
}

function readFormRecord() {
    return {
        productName: ui.productName.value.trim(),
        quantity: Number(ui.quantity.value),
        goodQuantity: Number(ui.goodQuantity.value),
        defectQuantity: Number(ui.defectQuantity.value),
        defectReason: ui.defectReason.value.trim(),
    };
}

function validateRecord(record) {
    if (!record.productName) {
        return "Укажите изделие.";
    }

    if (!Number.isInteger(record.quantity) || record.quantity <= 0) {
        return "Общее количество должно быть целым числом больше нуля.";
    }

    if (
        !Number.isInteger(record.goodQuantity) ||
        !Number.isInteger(record.defectQuantity) ||
        record.goodQuantity < 0 ||
        record.defectQuantity < 0
    ) {
        return "Количество годных изделий и брака должно быть целым неотрицательным числом.";
    }

    if (record.goodQuantity + record.defectQuantity !== record.quantity) {
        return "Ошибка: годных + брак должны быть равны общему количеству.";
    }

    return "";
}

function normalizeRecord(record) {
    const quantity = Number(record.quantity) || 0;
    const defectQuantity = Number(record.defectQuantity) || 0;

    return {
        id: Number(record.id),
        date: record.date || "",
        productName: String(record.productName || ""),
        quantity,
        goodQuantity: Number(record.goodQuantity) || 0,
        defectQuantity,
        defectPercent: Number.isFinite(Number(record.defectPercent))
            ? Number(record.defectPercent)
            : quantity > 0
                ? (defectQuantity / quantity) * 100
                : 0,
        defectReason: String(record.defectReason || ""),
    };
}

function jsonHeaders() {
    return {
        "Content-Type": "application/json; charset=utf-8",
    };
}

async function requestJson(url, options = {}) {
    const response = await fetch(url, {
        cache: "no-store",
        ...options,
    });

    let data = {};

    try {
        data = await response.json();
    } catch {
        data = {};
    }

    if (!response.ok) {
        throw new Error(data.error || `Ошибка сервера: HTTP ${response.status}`);
    }

    return data;
}

function renderAll() {
    renderProductionTable();
    renderStatistics();
}

function updateStorageStatus() {
    ui.storageStatus.textContent =
        `Данные сохраняются в SQLite. Записей: ${productionRecords.length}.`;
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
        appendActionsCell(row, record);

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

function appendActionsCell(row, record) {
    const cell = document.createElement("td");
    cell.className = "actions-cell";

    const actions = document.createElement("div");
    actions.className = "row-actions";

    actions.appendChild(
        createActionButton("Изменить", "edit", record.id)
    );
    actions.appendChild(
        createActionButton("Удалить", "delete", record.id, "delete")
    );

    cell.appendChild(actions);
    row.appendChild(cell);
}

function createActionButton(text, action, recordId, extraClass = "") {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = text;
    button.dataset.action = action;
    button.dataset.recordId = String(recordId);
    button.className = extraClass
        ? `row-action-button ${extraClass}`
        : "row-action-button";

    return button;
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

function formatDate(value) {
    const date = value instanceof Date ? value : new Date(value);

    if (Number.isNaN(date.getTime())) {
        return "—";
    }

    return new Intl.DateTimeFormat("ru-RU").format(date);
}
