# AW Client Report Portal — Guía de Contexto

## Propósito
Portal interno para EF (firma de planificación financiera en Atlanta). Permite al equipo (3 personas: Andrew, Rebecca, Maryann) ingresar datos financieros de ~6 clientes HNW/UHNW y generar PDFs trimestrales SACS (cashflow) y TCC (net worth). Reduce prep de reunión de 1 día a <1 hora.

## Stack FIJO (del PRD, NO modificar)
- Python + Flask
- HTML + CSS + JavaScript vanilla (SIN frameworks)
- SQLite en volumen Railway
- WeasyPrint para PDFs
- bcrypt para auth
- Deploy: Railway

## Reglas de Negocio Críticas (NO NEGOCIABLES)

### Cálculos SACS
- Inflow total = salario Client 1 + salario Client 2 (ambos cónyuges tienen salario individual)
- Excess = Inflow − Outflow (aparece en flecha azul hacia Private Reserve)
- Automated Transfer = Inflow − Outflow (ocurre en día X del mes, configurable por cliente, típico: 28)
- Private Reserve Target = (6 × Outflow mensual) + Σ(deducibles de TODAS las pólizas de seguro)
- Floor: $1,000 mínimo en cada cuenta bancaria (valor fijo, no cambia)

### Cálculos TCC
- Client 1 Retirement Total = Σ retirement accounts donde owner=client_1
- Client 2 Retirement Total = Σ retirement accounts donde owner=client_2
- Non-Retirement Total = Σ non-retirement accounts (EXCLUYE el trust)
- Grand Total Net Worth = C1 Retirement + C2 Retirement + Non-Retirement + Trust
- Liabilities Total = Σ liabilities (se muestra en caja separada, NUNCA se resta del net worth)

### Reglas específicas (del transcript)
- "we do not subtract liabilities from their net worth, they're just a separate box" (Rebecca 26:15)
- "we do not add the trust in [to non-retirement total]" (Rebecca 24:28)
- Cuentas con info desactualizada llevan asterisco (*) y el footer rojo: "* Indicates we do not have up to date information"
- Cada cuenta tiene su propia fecha "as of" (no fecha global del reporte)
- Algunas cuentas de inversión tienen sub-burbuja de Cash (balance en efectivo dentro de la cuenta)

## Modelo de Datos (schema lógico)

- **Client** (el "household"): id, property_address (trust), transfer_day_of_month, notes
- **Person**: client_id, role (client_1 | client_2), name, dob, ssn_last_4, monthly_salary
- **Account**: client_id, owner (client_1 | client_2 | joint), category (retirement | non_retirement | trust), type (IRA, Roth IRA, 401K, pension, brokerage, checking, savings, FICA…), account_number_last_4, label
- **AccountBalance**: account_id, report_id, balance, cash_balance, as_of_date, is_outdated
- **Liability**: client_id, name (custom: P Mortg, Mercedes, PNC…), interest_rate, balance, as_of_date
- **InsurancePolicy**: client_id, type, deductible
- **StaticFinancials**: client_id, agreed_monthly_outflow, private_reserve_target_override
- **QuarterlyReport**: client_id, report_date, snapshot de todos los valores usados, generated_at

## Especificaciones Visuales de PDFs

### SACS (2 páginas) — ver docs/references/sacs-page-1.png y sacs-page-2.png
**Página 1:**
- Título "Simple Automated Cashflow System (SACS)" + subtítulo "Client Example"
- Top-left: icono $ + desglose "$X - Client 1", "$Y - Client 2"
- Top-right: icono documentos + "X = Monthly Expenses"
- Círculo verde "INFLOW" con monto, etiqueta "$1,000 Floor"
- Flecha roja con label "X = $[outflow]/month* — Automated transfer on the [day]th"
- Círculo rojo "OUTFLOW" con monto, etiqueta "$1,000 Floor"
- Flecha azul con "$[excess]/mo*" hacia abajo
- Círculo azul "PRIVATE RESERVE" con icono piggy bank
- Footer: "MONTHLY CASHFLOW"

**Página 2:**
- Título repetido
- Círculo azul claro "FICA ACCOUNT" = balance Private Reserve, label "6X Monthly Expenses + Deductibles"
- Flecha bidireccional
- Círculo azul oscuro "INVESTMENT ACCOUNT" = balance Schwab (formato "$X+"), label "Remainder"

### TCC (1 página) — ver docs/references/tcc-sample.png
- Header: NAME, DATE
- Centro-superior: caja gris GRAND TOTAL + caja Liabilities total
- Top row: caja gris "Client 1 Retirement Only", burbuja verde Client 1, burbuja verde Client 2, caja gris "Client 2 Retirement Only"
- Sección RETIREMENT (superior, 2 cuadrantes): cuentas por cónyuge, cada una óvalo "ACCT # [tipo] $[balance] a/o [fecha]", con sub-burbuja "$X Cash" cuando aplica
- Centro: óvalo grande "Client 1 and Client 2 Family Trust $[valor] a/o [fecha]"
- Sección NON RETIREMENT (inferior, 2 cuadrantes): cuentas non-retirement por cónyuge
- Caja bordeada Liabilities: lista "Nombre $monto"
- Caja gris NON RETIREMENT TOTAL
- Footer rojo: "* Indicates we do not have up to date information"
- Layout dinámico: 1-6 retirement por cónyuge, 1-6 non-retirement, 0-N liabilities

## Convenciones de Código
- Routes en `app/routes/` por dominio (clients.py, reports.py, auth.py)
- Services en `app/services/` (calculations.py, pdf_generator.py)
- Templates Jinja2 con herencia desde `base.html`
- JS vanilla modular (un archivo por feature en `static/js/`)
- CSS con variables para branding en `:root`
- Nombres en inglés (código), comentarios en español cuando ayude
- Moneda siempre formateada con `${:,.2f}` o equivalente con comas

## Fuera de Scope V1 (NO implementar)
- Integraciones API (RightCapital, Schwab, Pinnacle, Zillow, Plaid)
- Onboarding automation
- Client-facing expense worksheet
- Auto-email mensual
