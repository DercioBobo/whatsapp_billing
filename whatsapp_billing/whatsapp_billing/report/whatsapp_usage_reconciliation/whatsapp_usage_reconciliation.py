# Copyright (c) 2024, Your Company and contributors
# For license information, please see license.txt
"""
WhatsApp Usage Reconciliation Report
=====================================
Compares every WhatsApp Usage Log against the CURRENT state of the Sales
Invoice it claims to belong to, and flags where they've drifted apart.

Drift happens because a Sales Invoice only tracks one active billing month
(``wb_billing_month``) and one billing line per Item. If usage for a second,
different month is fetched onto an invoice that already carries units for an
earlier month, the earlier month's Usage Log is left pointing at an invoice
whose line no longer reflects it. This report surfaces exactly that so it can
be corrected by hand — either by editing the Usage Log (re-link
``sales_invoice``, adjust ``total_billable_units`` / ``price_per_unit``) or by
fixing the invoice directly while it's still a draft.

Columns
-------
Customer | Log Month | Log Units | Log Amount | Log Status |
Invoice | Invoice Status | Invoice Month | Invoice Item Qty | Match
"""

import frappe
from frappe import _

MATCH_COLOUR = {
    "OK": "green",
    "Reconciled": "green",
    "Month Mismatch": "orange",
    "Units Mismatch": "orange",
    "Item Missing": "orange",
    "Config Missing": "orange",
    "Superseded": "red",
    "No Invoice": "red",
    "Invoice Cancelled": "red",
}

INVOICE_STATUS_COLOUR = {"Draft": "orange", "Submitted": "green", "Cancelled": "red"}
LOG_STATUS_COLOUR = {"Pending": "orange", "Confirmed": "green", "Cancelled": "red"}


def execute(filters=None):
    filters = filters or {}
    columns = _get_columns()
    data = _get_data(filters)
    summary = _get_summary(data)
    return columns, data, None, None, summary


# ─────────────────────────────────────────────────────────────────────────────
# Columns
# ─────────────────────────────────────────────────────────────────────────────


def _get_columns():
    return [
        {"fieldname": "customer", "label": _("Customer"), "fieldtype": "Link", "options": "Customer", "width": 180},
        {"fieldname": "billing_month", "label": _("Log Month"), "fieldtype": "Data", "width": 90},
        {"fieldname": "total_billable_units", "label": _("Log Units"), "fieldtype": "Int", "width": 90},
        {"fieldname": "total_amount", "label": _("Log Amount"), "fieldtype": "Currency", "options": "currency", "width": 130},
        {"fieldname": "log_status", "label": _("Log Status"), "fieldtype": "Data", "width": 100},
        {"fieldname": "sales_invoice", "label": _("Invoice"), "fieldtype": "Link", "options": "Sales Invoice", "width": 160},
        {"fieldname": "invoice_status", "label": _("Invoice Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "invoice_billing_month", "label": _("Invoice Month"), "fieldtype": "Data", "width": 100},
        {"fieldname": "invoice_item_qty", "label": _("Invoice Item Qty"), "fieldtype": "Data", "width": 120},
        {"fieldname": "match_status", "label": _("Match"), "fieldtype": "Data", "width": 130},
        {"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Data
# ─────────────────────────────────────────────────────────────────────────────


def _get_data(filters):
    conditions, values = _build_conditions(filters)
    where = f"WHERE {conditions}" if conditions else ""

    rows = frappe.db.sql(
        f"""
        SELECT
            wl.name                  AS log_name,
            wl.customer               AS customer,
            wl.billing_month          AS billing_month,
            wl.total_billable_units   AS total_billable_units,
            wl.total_amount           AS total_amount,
            wl.status                 AS log_status,
            wl.sales_invoice          AS sales_invoice,
            si.docstatus              AS invoice_docstatus,
            si.wb_billing_month       AS invoice_billing_month,
            si.wb_usage_log           AS invoice_linked_log,
            sii.qty                   AS invoice_item_qty,
            wbc.name                  AS config_name,
            COALESCE(wbc.currency, %(default_currency)s) AS currency
        FROM
            `tabWhatsApp Usage Log` wl
            LEFT JOIN `tabSales Invoice` si  ON si.name = wl.sales_invoice
            LEFT JOIN `tabWhatsApp Billing Config` wbc
                   ON wbc.customer = wl.customer AND wbc.is_active = 1
            LEFT JOIN `tabSales Invoice Item` sii
                   ON sii.parent = si.name AND sii.item_code = wbc.billing_item
        {where}
        ORDER BY
            wl.billing_month DESC,
            wl.customer       ASC
        """,
        {**values, "default_currency": frappe.defaults.get_global_default("currency")},
        as_dict=True,
    )

    mismatches_only = frappe.utils.cint(filters.get("mismatches_only"))

    result = []
    for row in rows:
        match = _match_status(row)

        if mismatches_only and match in ("OK", "Reconciled"):
            continue

        invoice_status = {0: "Draft", 1: "Submitted", 2: "Cancelled"}.get(row.invoice_docstatus, "—")

        result.append(
            {
                "customer": row.customer,
                "billing_month": row.billing_month,
                "total_billable_units": row.total_billable_units,
                "total_amount": row.total_amount,
                "currency": row.currency,
                "log_status": _pill(row.log_status, LOG_STATUS_COLOUR),
                "sales_invoice": row.sales_invoice or "",
                "invoice_status": _pill(invoice_status, INVOICE_STATUS_COLOUR) if row.sales_invoice else "",
                "invoice_billing_month": row.invoice_billing_month or "—",
                "invoice_item_qty": row.invoice_item_qty if row.invoice_item_qty is not None else "—",
                "match_status": _pill(match, MATCH_COLOUR),
            }
        )

    return result


def _match_status(row):
    """Classify how a Usage Log compares to the invoice it points at.

    Checked in priority order — a superseded link is worth flagging even if
    the month happens to still line up, since another fetch has already
    overwritten that invoice's billing line.

    A log with status "Confirmed" has been manually attested by a user (via
    "Mark as Billed") and always reads as reconciled, regardless of whether
    the numbers line up — that's the whole point of a manual override.
    """
    if row.log_status == "Confirmed":
        return "Reconciled"
    if not row.sales_invoice:
        return "No Invoice"
    if row.invoice_docstatus == 2:
        return "Invoice Cancelled"
    if row.invoice_linked_log and row.invoice_linked_log != row.log_name:
        return "Superseded"
    if not row.config_name:
        return "Config Missing"
    if row.invoice_item_qty is None:
        return "Item Missing"
    if (row.invoice_billing_month or "") != (row.billing_month or ""):
        return "Month Mismatch"
    if int(row.invoice_item_qty) != int(row.total_billable_units or 0):
        return "Units Mismatch"
    return "OK"


def _pill(label, colour_map):
    colour = colour_map.get(label, "grey")
    return f"<span class='indicator-pill {colour}'>{label}</span>"


def _build_conditions(filters):
    conditions = []
    values = {}

    if filters.get("billing_month"):
        conditions.append("wl.billing_month = %(billing_month)s")
        values["billing_month"] = filters["billing_month"]

    if filters.get("customer"):
        conditions.append("wl.customer = %(customer)s")
        values["customer"] = filters["customer"]

    return " AND ".join(conditions), values


# ─────────────────────────────────────────────────────────────────────────────
# Summary bar
# ─────────────────────────────────────────────────────────────────────────────


def _get_summary(data):
    if not data:
        return []

    total = len(data)
    ok_labels = (">OK<", ">Reconciled<")
    mismatches = sum(
        1 for row in data if not any(label in row.get("match_status", "") for label in ok_labels)
    )

    return [
        {"label": _("Logs Shown"), "value": total, "datatype": "Int", "indicator": "blue"},
        {
            "label": _("Mismatches"),
            "value": mismatches,
            "datatype": "Int",
            "indicator": "orange" if mismatches else "green",
        },
    ]
