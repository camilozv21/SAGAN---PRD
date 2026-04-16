/* Client form: married toggle, add/remove dynamic rows, client-side validation. */
(function () {
    'use strict';

    var form = document.getElementById('client-form');
    if (!form) return;

    // ----- 1. Married toggle --------------------------------------------
    var marriedToggle = form.querySelector('input[name="is_married"]');
    var client2Section = form.querySelector('.client-2-section');

    function syncMarriedState() {
        var married = marriedToggle.checked;
        if (client2Section) {
            client2Section.hidden = !married;
        }
        // Show/hide the Client 2 option inside every owner select.
        form.querySelectorAll('select.select-owner').forEach(function (sel) {
            Array.from(sel.options).forEach(function (opt) {
                if (opt.hasAttribute('data-c2-only')) {
                    opt.hidden = !married;
                    opt.disabled = !married;
                    if (!married && sel.value === 'client_2') {
                        sel.value = 'client_1';
                    }
                }
            });
        });
        // Required-ness for Client 2 fields.
        ['c2_name', 'c2_monthly_salary'].forEach(function (name) {
            var input = form.querySelector('[name="' + name + '"]');
            if (input) input.required = married;
        });
    }

    if (marriedToggle) {
        marriedToggle.addEventListener('change', syncMarriedState);
    }

    // ----- 2. Add / remove dynamic rows ---------------------------------
    var ROW_TEMPLATES = {
        retirement: 'tpl-retirement-row',
        nonret: 'tpl-nonret-row',
        liability: 'tpl-liability-row',
        insurance: 'tpl-insurance-row'
    };

    form.querySelectorAll('[data-add-row]').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var key = btn.getAttribute('data-add-row');
            var tplId = ROW_TEMPLATES[key];
            var tpl = document.getElementById(tplId);
            var container = form.querySelector('[data-rows="' + key + '"]');
            if (!tpl || !container) return;
            var fragment = tpl.content.cloneNode(true);
            container.appendChild(fragment);
            syncMarriedState();
        });
    });

    form.addEventListener('click', function (event) {
        var target = event.target;
        if (target.classList && target.classList.contains('btn-row-remove')) {
            var row = target.closest('.dynamic-row');
            if (row && confirm('Remove this row?')) {
                row.remove();
            }
        }
    });

    // ----- 3. Client-side validation ------------------------------------
    function showError(msg) {
        var slot = document.getElementById('client-form-errors');
        if (!slot) {
            slot = document.createElement('div');
            slot.id = 'client-form-errors';
            slot.className = 'inline-errors';
            form.insertBefore(slot, form.firstChild);
        }
        slot.textContent = msg;
        slot.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    function clearError() {
        var slot = document.getElementById('client-form-errors');
        if (slot) slot.textContent = '';
    }

    form.addEventListener('submit', function (event) {
        clearError();
        var married = marriedToggle && marriedToggle.checked;

        var c1Name = form.querySelector('[name="c1_name"]').value.trim();
        var c1Salary = form.querySelector('[name="c1_monthly_salary"]').value;
        if (!c1Name) {
            event.preventDefault();
            showError('Client 1 name is required.');
            return;
        }
        if (c1Salary === '' || isNaN(parseFloat(c1Salary)) || parseFloat(c1Salary) < 0) {
            event.preventDefault();
            showError('Client 1 monthly salary must be a number >= 0.');
            return;
        }

        if (married) {
            var c2Name = form.querySelector('[name="c2_name"]').value.trim();
            var c2Salary = form.querySelector('[name="c2_monthly_salary"]').value;
            if (!c2Name) {
                event.preventDefault();
                showError('Client 2 name is required (household is marked as married).');
                return;
            }
            if (c2Salary === '' || isNaN(parseFloat(c2Salary)) || parseFloat(c2Salary) < 0) {
                event.preventDefault();
                showError('Client 2 monthly salary must be a number >= 0.');
                return;
            }
        }

        // SSN: if filled, must be 4 digits.
        var ssnOk = true;
        form.querySelectorAll('[name="c1_ssn_last_4"], [name="c2_ssn_last_4"]').forEach(function (inp) {
            var v = inp.value.trim();
            if (v !== '' && !/^\d{4}$/.test(v)) ssnOk = false;
        });
        if (!ssnOk) {
            event.preventDefault();
            showError('SSN must be exactly 4 digits, or left empty.');
            return;
        }

        // Outflow required.
        var outflow = form.querySelector('[name="agreed_monthly_outflow"]').value;
        if (outflow === '' || isNaN(parseFloat(outflow)) || parseFloat(outflow) < 0) {
            event.preventDefault();
            showError('Agreed monthly outflow is required (>= 0).');
            return;
        }

        // If single, strip any rows with owner=client_2 before submit.
        if (!married) {
            form.querySelectorAll('select.select-owner').forEach(function (sel) {
                if (sel.value === 'client_2') {
                    var row = sel.closest('.dynamic-row');
                    if (row) row.remove();
                }
            });
        }
    });

    // ----- 4. Initial state ---------------------------------------------
    syncMarriedState();
})();
