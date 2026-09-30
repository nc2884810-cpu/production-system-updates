document.addEventListener("DOMContentLoaded", () => {
    const addProductionButton = document.getElementById("addProductionButton");
    const productionModal = document.getElementById("productionModal");
    const closeModalButton = document.getElementById("closeModalButton");
    const cancelButton = document.getElementById("cancelButton");
    const productionForm = document.getElementById("productionForm");
    const formMessage = document.getElementById("formMessage");
    const currentDate = document.getElementById("currentDate");

    currentDate.textContent = "Сегодня: " + new Date().toLocaleDateString("ru-RU");

    function openModal() {
        productionModal.classList.remove("hidden");
        productionModal.setAttribute("aria-hidden", "false");
        formMessage.textContent = "";
        formMessage.className = "form-message";
        document.getElementById("productName").focus();
    }

    function closeModal() {
        productionModal.classList.add("hidden");
        productionModal.setAttribute("aria-hidden", "true");
        productionForm.reset();
        formMessage.textContent = "";
        formMessage.className = "form-message";
    }

    addProductionButton.addEventListener("click", openModal);
    closeModalButton.addEventListener("click", closeModal);
    cancelButton.addEventListener("click", closeModal);

    productionModal.addEventListener("click", (event) => {
        if (event.target === productionModal) {
            closeModal();
        }
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && !productionModal.classList.contains("hidden")) {
            closeModal();
        }
    });

    productionForm.addEventListener("submit", (event) => {
        event.preventDefault();

        const quantity = Number(document.getElementById("quantity").value);
        const goodQuantity = Number(document.getElementById("goodQuantity").value);
        const defectQuantity = Number(document.getElementById("defectQuantity").value);

        if (goodQuantity + defectQuantity !== quantity) {
            formMessage.textContent =
                "Ошибка: годных + брак должны быть равны общему количеству.";
            formMessage.className = "form-message error";
            return;
        }

        const defectPercent = quantity > 0
            ? ((defectQuantity / quantity) * 100).toFixed(2)
            : "0.00";

        formMessage.textContent =
            `Проверка пройдена. Процент брака: ${defectPercent}%`;
        formMessage.className = "form-message success";
    });
});
