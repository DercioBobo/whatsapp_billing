# Copyright (c) 2024, Your Company and contributors
# For license information, please see license.txt
"""
WhatsApp Live Usage Report
==========================
Fetches data directly from the external API for every active WhatsApp Billing
Config and shows a live breakdown by customer and month.

Unlike the "WhatsApp Monthly Usage" report (which reads the stored Usage Log),
this report is always current — every refresh re-hits the API.

Columns
-------
Customer | Month | Sessions | Billable Units | Expected Amount | Invoice | Invoice Status
"""

from collections import defaultdict
from datetime import datetime

import frappe
import requests
from frappe import _


def execute(filters=None):
    filters = filters or {}
    columns = _get_columns()
    data, warnings = _get_data(filters)
    summary = _get_summary(data)

    # Surface API errors as a yellow message above the table
    message = None
    if warnings:
        items = "".join(f"<li>{w}</li>" for w in warnings)
        message = f"<div class='alert alert-warning'><b>Some APIs could not be reached:</b><ul>{items}</ul></div>"

    return columns, data, message, None, summary


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
            "fieldname": "total_sessions",
            "label": _("Sessions"),
            "fieldtype": "Int",
            "width": 100,
        },
        {
            "fieldname": "billable_units",
            "label": _("Billable Units"),
            "fieldtype": "Int",
            "width": 120,
        },
        {
            "fieldname": "expected_amount",
            "label": _("Expected Amount"),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 150,
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
            "width": 130,
        },
        {
            "fieldname": "currency",
            "label": _("Currency"),
            "fieldtype": "Link",
            "options": "Currency",
            "hidden": 1,
        },
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Data
# ─────────────────────────────────────────────────────────────────────────────


def _get_data(filters):
    # Load active configs, optionally filtered by customer
    config_filters = {"is_active": 1}
    if filters.get("customer"):
        config_filters["customer"] = filters["customer"]

    configs = frappe.get_all(
        "WhatsApp Billing Config",
        filters=config_filters,
        fields=["name", "customer", "api_endpoint", "api_token", "price_per_unit", "currency"],
    )

    if not configs:
        return [], []

    # Load all wb-enabled Sales Invoices once (to match against months later)
    # Structure: {(customer, billing_month): (invoice_name, docstatus)}
    invoice_map = _build_invoice_map()

    rows = []
    warnings = []
    billing_month_filter = filters.get("billing_month") or ""

    for config in configs:
        try:
            raw_data = _fetch_api(config)
        except Exception as exc:
            warnings.append(f"<b>{config.customer}</b>: {exc}")
            continue

        # Aggregate: { billing_month: { unique_pairs: set, sessions: int } }
        month_agg = _aggregate(raw_data, billing_month_filter)

        price_per_unit = config.price_per_unit or 0
        currency = config.currency or frappe.defaults.get_global_default("currency")

        for month in sorted(month_agg.keys(), reverse=True):
            agg = month_agg[month]
            billable_units = len(agg["pairs"])
            total_sessions = agg["sessions"]
            expected_amount = billable_units * price_per_unit

            invoice_name, docstatus = invoice_map.get(
                (config.customer, month), (None, None)
            )

            invoice_status_html = _invoice_status_html(invoice_name, docstatus)

            rows.append(
                {
                    "customer": config.customer,
                    "billing_month": month,
                    "total_sessions": total_sessions,
                    "billable_units": billable_units,
                    "expected_amount": expected_amount,
                    "currency": currency,
                    "sales_invoice": invoice_name or "",
                    "invoice_status": invoice_status_html,
                }
            )

    return rows, warnings


def _fetch_api(config):
    """Call the API endpoint and return a normalised list of records."""
    headers = {"Accept": "application/json"}
    if config.get("api_token"):
        # Reload as full doc to use get_password
        full = frappe.get_doc("WhatsApp Billing Config", config.name)
        headers["Authorization"] = f"Bearer {full.get_password('api_token')}"

    try:
        response = requests.get(config.api_endpoint, headers=headers, timeout=30)
        response.raise_for_status()
        raw = response.json()
    except requests.exceptions.Timeout:
        raise Exception("API timed out (30 s)")
    except requests.exceptions.ConnectionError:
        raise Exception(f"Could not connect to {config.api_endpoint}")
    except requests.exceptions.HTTPError as e:
        raise Exception(f"HTTP {e.response.status_code}")
    except Exception as e:
        raise Exception(str(e))

    # Normalise: accept plain list or wrapper dict
    if isinstance(raw, dict):
        for key in ("data", "results", "records", "items"):
            if key in raw and isinstance(raw[key], list):
                return raw[key]
        return [raw]

    if isinstance(raw, list):
        return raw

    raise Exception("Unexpected API response format")


def _aggregate(raw_data, billing_month_filter):
    """
    Group records by YYYY-MM and compute:
      - pairs    : set of unique (customer_id, date) — drives billable_units
      - sessions : sum of total_sessoes_in_day — total interactions
    """
    agg = defaultdict(lambda: {"pairs": set(), "sessions": 0})

    for record in raw_data:
        if not isinstance(record, dict):
            continue

        day_str = str(record.get("day", "")).strip()
        if not day_str:
            continue

        try:
            record_date = datetime.strptime(day_str[:10], "%Y-%m-%d")
        except ValueError:
            continue

        month_key = record_date.strftime("%Y-%m")

        # Apply month filter if set
        if billing_month_filter and month_key != billing_month_filter:
            continue

        customer_id = record.get("customer_id")
        if customer_id is None:
            continue

        date_key = record_date.strftime("%Y-%m-%d")
        agg[month_key]["pairs"].add((customer_id, date_key))
        agg[month_key]["sessions"] += int(record.get("total_sessoes_in_day") or 0)

    return agg


def _build_invoice_map():
    """
    Return a dict mapping (customer, billing_month) → (invoice_name, docstatus)
    for all wb-enabled Sales Invoices.
    """
    invoices = frappe.db.sql(
        """
        SELECT name, customer, wb_billing_month, docstatus
        FROM   `tabSales Invoice`
        WHERE  wb_enabled = 1
          AND  wb_billing_month IS NOT NULL
          AND  wb_billing_month != ''
        """,
        as_dict=True,
    )
    return {
        (inv.customer, inv.wb_billing_month): (inv.name, inv.docstatus)
        for inv in invoices
    }


def _invoice_status_html(invoice_name, docstatus):
    if not invoice_name:
        return "<span class='indicator-pill grey'>Not Created</span>"

    labels = {0: ("Draft", "orange"), 1: ("Submitted", "green"), 2: ("Cancelled", "red")}
    label, colour = labels.get(docstatus, ("Unknown", "grey"))
    return f"<span class='indicator-pill {colour}'>{label}</span>"


# ─────────────────────────────────────────────────────────────────────────────
# Summary bar
# ─────────────────────────────────────────────────────────────────────────────


def _get_summary(data):
    if not data:
        return []

    total_sessions = sum(r.get("total_sessions") or 0 for r in data)
    total_units = sum(r.get("billable_units") or 0 for r in data)
    total_expected = sum(r.get("expected_amount") or 0 for r in data)
    customers = len({r.get("customer") for r in data if r.get("customer")})
    not_invoiced = sum(1 for r in data if not r.get("sales_invoice"))

    return [
        {
            "label": _("Customers"),
            "value": customers,
            "datatype": "Int",
            "indicator": "blue",
        },
        {
            "label": _("Total Sessions"),
            "value": total_sessions,
            "datatype": "Int",
            "indicator": "blue",
        },
        {
            "label": _("Total Billable Units"),
            "value": total_units,
            "datatype": "Int",
            "indicator": "green",
        },
        {
            "label": _("Total Expected Amount"),
            "value": total_expected,
            "datatype": "Currency",
            "indicator": "green",
        },
        {
            "label": _("Months Without Invoice"),
            "value": not_invoiced,
            "datatype": "Int",
            "indicator": "orange" if not_invoiced else "green",
        },
    ]
