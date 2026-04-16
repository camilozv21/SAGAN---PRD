/* Real-time SACS/TCC calculations for the quarterly report entry form.
 *
 * Mirrors app/services/calculations.py — any change to the Python rules must
 * be reflected here and vice versa. Kept in plain JS (no framework) per PRD. */
(function () {
    "use strict";

    const form = document.getElementById("report-entry-form");
    if (!form) return;

    const isMarried = form.dataset.isMarried === "true";
    let deductibles = [];
    try {
        deductibles = JSON.parse(form.dataset.deductibles || "[]").map(toNumber);
    } catch (e) {
        deductibles = [];
    }

    const generateBtn = document.getElementById("btn-generate");
    const validationNote = document.getElementById("panel-validation");

    function toNumber(raw) {
        if (raw === null || raw === undefined) return 0;
        const cleaned = String(raw).replace(/[$,]/g, "").trim();
        if (cleaned === "") return 0;
        const n = Number(cleaned);
        return Number.isFinite(n) ? n : 0;
    }

    function money(value) {
        const n = Number(value) || 0;
        const sign = n < 0 ? "-" : "";
        return sign + "$" + Math.abs(n).toLocaleString("en-US", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
    }

    function sumGroup(group) {
        const inputs = form.querySelectorAll(
            'input.js-sum-input[data-sum-group="' + group + '"]'
        );
        let total = 0;
        inputs.forEach((el) => { total += toNumber(el.value); });
        return total;
    }

    function sumRetirementByOwner(owner) {
        const rows = form.querySelectorAll(
            '.balance-row[data-group="' + owner + '"]'
        );
        let total = 0;
        rows.forEach((row) => {
            const balance = row.querySelector(
                'input.js-balance-input[name$="_balance"]'
            );
            if (balance) total += toNumber(balance.value);
        });
        return total;
    }

    function recalculate() {
        const salaryC1 = toNumber(form.querySelector('[name="salary_c1"]')?.value);
        const salaryC2 = isMarried
            ? toNumber(form.querySelector('[name="salary_c2"]')?.value)
            : 0;
        const outflow = toNumber(form.querySelector('[name="outflow"]')?.value);

        // --- SACS --------------------------------------------------------
        const inflow = salaryC1 + salaryC2;
        const excess = inflow - outflow;
        const deductiblesTotal = deductibles.reduce((a, b) => a + b, 0);
        const target = 6 * outflow + deductiblesTotal;

        // --- TCC ---------------------------------------------------------
        const c1Retirement = sumGroup("c1_retirement");
        const c2Retirement = sumGroup("c2_retirement");
        const nonRetirement = sumGroup("non_retirement");
        const trust = sumGroup("trust");
        // Grand total = C1 retirement + C2 retirement + non-retirement + trust
        // Liabilities NEVER enter this sum (PRD: Rebecca 26:15).
        const grandTotal = c1Retirement + c2Retirement + nonRetirement + trust;
        const liabilitiesTotal = sumGroup("liabilities");

        setText("salary_c1", money(salaryC1));
        setText("salary_c2", money(salaryC2));
        setText("outflow", money(outflow));
        setText("inflow", money(inflow));
        setText("excess", money(excess));
        setText("deductibles_total", money(deductiblesTotal));
        setText("target", money(target));

        setText("c1_retirement", money(c1Retirement));
        setText("c2_retirement", money(c2Retirement));
        setText("non_retirement", money(nonRetirement));
        setText("trust", money(trust));
        setText("grand_total", money(grandTotal));
        setText("liabilities_total", money(liabilitiesTotal));

        // Negative excess: tint red so the user sees the household is spending
        // more than it earns.
        const excessCell = form.querySelector('[data-calc-state="excess"]');
        if (excessCell) {
            excessCell.classList.toggle("calc-negative", excess < 0);
        }

        updateValidation();
    }

    function setText(key, value) {
        const nodes = form.querySelectorAll('[data-calc="' + key + '"]');
        nodes.forEach((n) => { n.textContent = value; });
    }

    function updateValidation() {
        const required = form.querySelectorAll("input[required]");
        const missing = [];
        required.forEach((el) => {
            if (!el.value.trim()) {
                missing.push(el);
                el.classList.add("is-missing");
            } else {
                el.classList.remove("is-missing");
            }
        });

        if (!generateBtn) return;
        if (missing.length === 0) {
            generateBtn.disabled = false;
            if (validationNote) validationNote.textContent = "";
        } else {
            generateBtn.disabled = true;
            if (validationNote) {
                validationNote.textContent =
                    missing.length +
                    " required field" +
                    (missing.length === 1 ? "" : "s") +
                    " empty.";
            }
        }
    }

    function handleUseLast(event) {
        const btn = event.target.closest(".btn-use-last");
        if (!btn) return;
        event.preventDefault();
        const targetName = btn.dataset.target;
        const value = btn.dataset.value;
        if (!targetName || value === undefined) return;
        const input = form.querySelector('[name="' + targetName + '"]');
        if (!input) return;
        input.value = value;
        input.dispatchEvent(new Event("input", { bubbles: true }));
    }

    form.addEventListener("input", recalculate);
    form.addEventListener("change", recalculate);
    form.addEventListener("click", handleUseLast);

    // Initial paint: run once so the panel reflects prefilled values.
    recalculate();
})();
