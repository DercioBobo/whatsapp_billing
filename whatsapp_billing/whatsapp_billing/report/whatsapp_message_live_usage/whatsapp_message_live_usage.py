# Copyright (c) 2024, Your Company and contributors
# For license information, please see license.txt
"""
WhatsApp Message Live Usage Report
===================================
Fetches data directly from the external API for every active WhatsApp
Message Billing Config and shows a live monthly message-volume breakdown.

Unlike the "WhatsApp Message Monthly Usage" report (which reads the stored
Usage Log), this report is always current — every refresh re-hits the API.

Columns
-------
Customer | Month | Total Messages | Expected Amount | Invoice | Invoice Status
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
            "fieldname": "total_messages",
            "label": _("Total Messages"),
            "fieldtype": "Int",
            "width": 130,
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
        "WhatsApp Message Billing Config",
        filters=config_filters,
        fields=["name", "customer", "api_endpoint", "api_token", "price_per_message", "currency"],
    )

    if not configs:
        return [], []

    # Load all billed months once (to match against API months later)
    # Structure: {(customer, billing_month): (invoice_name, docstatus, log_status)}
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

        member_counts = _get_member_counts(config.name)

        # Aggregate: { billing_month: total_messages } — reach-adjusted the
        # same way apply_message_usage_to_invoice computes it, so "Expected
        # Amount" here always matches what actually lands on the invoice.
        month_agg = _aggregate(raw_data, billing_month_filter, member_counts)

        price_per_message = config.price_per_message or 0
        currency = config.currency or frappe.defaults.get_global_default("currency")

        for month in sorted(month_agg.keys(), reverse=True):
            total_messages = month_agg[month]
            expected_amount = total_messages * price_per_message

            invoice_name, docstatus, log_status = invoice_map.get(
                (config.customer, month), (None, None, None)
            )

            invoice_status_html = _invoice_status_html(invoice_name, docstatus, log_status)

            rows.append(
                {
                    "customer": config.customer,
                    "billing_month": month,
                    "total_messages": total_messages,
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
        full = frappe.get_doc("WhatsApp Message Billing Config", config.name)
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


def _get_member_counts(config_name):
    """Return {phone_number: member_count} from the config's Group Member
    Counts child table. Any phone_number not present defaults to 1 wherever
    this lookup is used — same rule as apply_message_usage_to_invoice.
    """
    rows = frappe.get_all(
        "WhatsApp Message Group Member Count",
        filters={"parent": config_name, "parenttype": "WhatsApp Message Billing Config"},
        fields=["phone_number", "member_count"],
    )
    return {row.phone_number: row.member_count or 1 for row in rows if row.phone_number}


def _aggregate(raw_data, billing_month_filter, member_counts=None):
    """
    Group records by YYYY-MM and sum (total_mensagens_in_day × member_count)
    across every phone_number/group — the endpoint is already scoped to one
    customer, so every record counts towards that customer's bill. A
    phone_number with no entry in member_counts is treated as reaching 1
    recipient per message.
    """
    member_counts = member_counts or {}
    agg = defaultdict(int)

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

        member_count = member_counts.get(record.get("phone_number"), 1)
        agg[month_key] += int(record.get("total_mensagens_in_day") or 0) * member_count

    return agg


def _build_invoice_map():
    """
    Return a dict mapping (customer, billing_month) → (invoice_name, docstatus, log_status)
    sourced from WhatsApp Message Usage Log — the actual record of "this month
    was billed via this invoice" — rather than the invoice's own
    ``wmb_billing_month`` field, which only ever holds the single
    most-recently-fetched month and drifts out of sync if a different month is
    later fetched onto the same invoice.

    This also covers invoices created manually via "Mark as Billed" (see
    ``mark_message_usage_as_billed``), which creates a Usage Log without
    touching the invoice's ``wmb_*`` fields at all.
    """
    rows = frappe.db.sql(
        """
        SELECT wl.customer, wl.billing_month, wl.sales_invoice, wl.status AS log_status, si.docstatus
        FROM   `tabWhatsApp Message Usage Log` wl
        LEFT JOIN `tabSales Invoice` si ON si.name = wl.sales_invoice
        WHERE  wl.sales_invoice IS NOT NULL
          AND  wl.sales_invoice != ''
        """,
        as_dict=True,
    )
    return {
        (row.customer, row.billing_month): (row.sales_invoice, row.docstatus, row.log_status)
        for row in rows
    }


def _invoice_status_html(invoice_name, docstatus, log_status):
    if not invoice_name:
        return "<span class='indicator-pill grey'>Not Created</span>"

    if log_status == "Confirmed":
        return "<span class='indicator-pill green'>Confirmed</span>"

    labels = {0: ("Draft", "orange"), 1: ("Submitted", "green"), 2: ("Cancelled", "red")}
    label, colour = labels.get(docstatus, ("Unknown", "grey"))
    return f"<span class='indicator-pill {colour}'>{label}</span>"


# ─────────────────────────────────────────────────────────────────────────────
# Summary bar
# ─────────────────────────────────────────────────────────────────────────────


def _get_summary(data):
    if not data:
        return []

    total_messages = sum(r.get("total_messages") or 0 for r in data)
    total_expected = sum(r.get("expected_amount") or 0 for r in data)
    customers = len({r.get("customer") for r in data if r.get("customer")})
    not_invoiced = sum(1 for r in data if not r.get("sales_invoice"))
    # Total Expected Amount covers every month regardless of billing status —
    # it never shrinks. This is the figure that actually reflects reconciliation:
    # only months still lacking a linked invoice count towards it.
    outstanding_amount = sum(r.get("expected_amount") or 0 for r in data if not r.get("sales_invoice"))

    return [
        {
            "label": _("Customers"),
            "value": customers,
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
        {
            "label": _("Outstanding Amount"),
            "value": outstanding_amount,
            "datatype": "Currency",
            "indicator": "orange" if outstanding_amount else "green",
        },
    ]
