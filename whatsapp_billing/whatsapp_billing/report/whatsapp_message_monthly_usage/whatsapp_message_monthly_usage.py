# Copyright (c) 2024, Your Company and contributors
# For license information, please see license.txt

import frappe
from frappe import _


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
        {
            "fieldname": "customer",
            "label": _("Customer"),
            "fieldtype": "Link",
            "options": "Customer",
            "width": 200,
        },
        {
            "fieldname": "billing_month",
            "label": _("Month"),
            "fieldtype": "Data",
            "width": 100,
        },
        {
            "fieldname": "total_messages",
            "label": _("Messages"),
            "fieldtype": "Int",
            "width": 100,
        },
        {
            "fieldname": "price_per_message",
            "label": _("Rate"),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 120,
        },
        {
            "fieldname": "total_amount",
            "label": _("Amount"),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 140,
        },
        {
            "fieldname": "sales_invoice",
            "label": _("Invoice"),
            "fieldtype": "Link",
            "options": "Sales Invoice",
            "width": 160,
        },
        {
            "fieldname": "invoice_status",
            "label": _("Invoice Status"),
            "fieldtype": "Data",
            "width": 110,
        },
        {
            "fieldname": "status",
            "label": _("Log Status"),
            "fieldtype": "Data",
            "width": 100,
        },
        # Hidden — used by Currency columns to pick the right symbol
        {
            "fieldname": "currency",
            "label": _("Currency"),
            "fieldtype": "Link",
            "options": "Currency",
            "width": 80,
            "hidden": 1,
        },
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
            wl.customer,
            wl.billing_month,
            wl.total_messages,
            wl.price_per_message,
            wl.total_amount,
            wl.sales_invoice,
            CASE si.docstatus
                WHEN 0 THEN 'Draft'
                WHEN 1 THEN 'Submitted'
                WHEN 2 THEN 'Cancelled'
                ELSE '—'
            END  AS invoice_status,
            wl.status,
            COALESCE(wmc.currency, %(default_currency)s) AS currency
        FROM
            `tabWhatsApp Message Usage Log` wl
            LEFT JOIN `tabSales Invoice`       si  ON si.name  = wl.sales_invoice
            LEFT JOIN `tabWhatsApp Message Billing Config` wmc ON wmc.customer = wl.customer
                                                              AND wmc.is_active = 1
        {where}
        ORDER BY
            wl.billing_month DESC,
            wl.customer       ASC
        """,
        {**values, "default_currency": frappe.defaults.get_global_default("currency")},
        as_dict=True,
    )

    # Colour-code invoice_status so it's readable at a glance
    status_colour = {
        "Draft": "orange",
        "Submitted": "green",
        "Cancelled": "red",
    }
    log_colour = {
        "Pending": "orange",
        "Confirmed": "green",
        "Cancelled": "red",
    }

    for row in rows:
        inv_colour = status_colour.get(row.invoice_status, "grey")
        log_col = log_colour.get(row.status, "grey")
        row["invoice_status"] = f"<span class='indicator-pill {inv_colour}'>{row.invoice_status}</span>"
        row["status"] = f"<span class='indicator-pill {log_col}'>{row.status}</span>"

    return rows


def _build_conditions(filters):
    conditions = []
    values = {}

    if filters.get("billing_month"):
        conditions.append("wl.billing_month = %(billing_month)s")
        values["billing_month"] = filters["billing_month"]

    if filters.get("customer"):
        conditions.append("wl.customer = %(customer)s")
        values["customer"] = filters["customer"]

    if filters.get("status"):
        conditions.append("wl.status = %(status)s")
        values["status"] = filters["status"]

    if filters.get("invoice_status"):
        docstatus_map = {"Draft": 0, "Submitted": 1, "Cancelled": 2}
        ds = docstatus_map.get(filters["invoice_status"])
        if ds is not None:
            conditions.append("si.docstatus = %(docstatus)s")
            values["docstatus"] = ds

    return " AND ".join(conditions), values


# ─────────────────────────────────────────────────────────────────────────────
# Summary bar (shown above the table)
# ─────────────────────────────────────────────────────────────────────────────


def _get_summary(data):
    if not data:
        return []

    total_messages = sum(row.get("total_messages") or 0 for row in data)
    total_amount = sum(row.get("total_amount") or 0 for row in data)
    customers = len({row.get("customer") for row in data if row.get("customer")})
    months = len({row.get("billing_month") for row in data if row.get("billing_month")})

    return [
        {
            "label": _("Customers"),
            "value": customers,
            "datatype": "Int",
            "indicator": "blue",
        },
        {
            "label": _("Months"),
            "value": months,
            "datatype": "Int",
            "indicator": "blue",
        },
        {
            "label": _("Total Messages"),
            "value": total_messages,
            "datatype": "Int",
            "indicator": "green",
        },
        {
            "label": _("Total Amount"),
            "value": total_amount,
            "datatype": "Currency",
            "indicator": "green",
        },
    ]
