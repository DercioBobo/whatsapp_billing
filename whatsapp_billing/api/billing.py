# Copyright (c) 2024, Your Company and contributors
# For license information, please see license.txt
"""
WhatsApp Billing API
====================
Exposes three whitelisted endpoints called from the Sales Invoice client script.

Billing logic
-------------
  - 1 billable unit = 1 unique (customer_id, date) pair in the billing month
  - total_amount = total_units × price_per_unit
"""

import json
from collections import defaultdict
from datetime import datetime

import frappe
import requests


# ─────────────────────────────────────────────────────────────────────────────
# Public helpers
# ─────────────────────────────────────────────────────────────────────────────


@frappe.whitelist()
def get_config_for_customer(customer):
    """Return the active WhatsApp Billing Config for *customer*, or None.

    Used by the client script to auto-populate ``wb_config`` when
    ``wb_enabled`` is toggled on or the customer changes.
    """
    if not customer:
        return None

    config = frappe.db.get_value(
        "WhatsApp Billing Config",
        {"customer": customer, "is_active": 1},
        ["name", "price_per_unit", "currency", "billing_item"],
        as_dict=True,
    )
    return config


# ─────────────────────────────────────────────────────────────────────────────
# Core billing logic
# ─────────────────────────────────────────────────────────────────────────────


@frappe.whitelist()
def get_usage(invoice_name, billing_month):
    """Fetch and calculate usage from the external API.

    Does **not** modify any document — purely reads and computes.

    Parameters
    ----------
    invoice_name : str
        Name of the Sales Invoice that has ``wb_enabled = 1``.
    billing_month : str
        Target month in ``YYYY-MM`` format.

    Returns
    -------
    dict
        ``{total_units, breakdown, price_per_unit, currency, item_code}``
    """
    invoice = frappe.get_doc("Sales Invoice", invoice_name)

    # ── Guard clauses ────────────────────────────────────────────────────────
    if not invoice.get("wb_enabled"):
        frappe.throw(
            f"Invoice {invoice_name} does not have WhatsApp Billing enabled.",
            title="Not a WhatsApp Billing Invoice",
        )

    if not invoice.get("wb_config"):
        frappe.throw(
            "Please set the Billing Config on the invoice before fetching usage.",
            title="Missing Billing Config",
        )

    config = frappe.get_doc("WhatsApp Billing Config", invoice.wb_config)

    if not config.is_active:
        frappe.throw(
            f"Billing Config '{config.name}' is inactive. Activate it before billing.",
            title="Inactive Config",
        )

    # ── Parse & validate billing_month ──────────────────────────────────────
    try:
        year_str, month_str = billing_month.split("-")
        target_year = int(year_str)
        target_month = int(month_str)
        if not (1 <= target_month <= 12):
            raise ValueError
    except (ValueError, AttributeError):
        frappe.throw(
            f"Invalid billing month '{billing_month}'. Expected YYYY-MM (e.g. 2026-02).",
            title="Invalid Billing Month",
        )

    # ── Fetch data from external API ─────────────────────────────────────────
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if config.get("api_token"):
        headers["Authorization"] = f"Bearer {config.get_password('api_token')}"

    try:
        response = requests.get(
            config.api_endpoint, headers=headers, timeout=60
        )
        response.raise_for_status()
        raw_data = response.json()
    except requests.exceptions.Timeout:
        frappe.throw(
            "API request timed out (60 s). Check the endpoint or try again.",
            title="API Timeout",
        )
    except requests.exceptions.ConnectionError as exc:
        frappe.throw(
            f"Could not connect to API endpoint: {config.api_endpoint}\n{exc}",
            title="Connection Error",
        )
    except requests.exceptions.HTTPError as exc:
        frappe.throw(
            f"API returned an error: {exc}",
            title="API HTTP Error",
        )
    except Exception as exc:
        frappe.throw(
            f"Unexpected error while fetching API data: {exc}",
            title="API Error",
        )

    # ── Normalise: the API may return a list or a wrapper dict ───────────────
    if isinstance(raw_data, dict):
        for key in ("data", "results", "records", "items"):
            if key in raw_data and isinstance(raw_data[key], list):
                raw_data = raw_data[key]
                break
        else:
            raw_data = [raw_data]

    if not isinstance(raw_data, list):
        frappe.throw(
            "Unexpected API response format — expected a JSON array.",
            title="API Format Error",
        )

    # ── Filter to billing_month and count unique (customer_id, date) pairs ──
    unique_pairs: set = set()
    daily_customers: dict = defaultdict(set)

    for record in raw_data:
        if not isinstance(record, dict):
            continue

        day_str = str(record.get("day", "")).strip()
        if not day_str:
            continue

        # Accept "2026-03-04 02:00:00" or "2026-03-04"
        try:
            record_date = datetime.strptime(day_str[:10], "%Y-%m-%d")
        except ValueError:
            continue

        if record_date.year != target_year or record_date.month != target_month:
            continue

        customer_id = record.get("customer_id")
        if customer_id is None:
            continue

        date_key = record_date.strftime("%Y-%m-%d")
        unique_pairs.add((customer_id, date_key))
        daily_customers[date_key].add(customer_id)

    total_units = len(unique_pairs)

    # ── Build sorted daily breakdown ─────────────────────────────────────────
    breakdown = sorted(
        [
            {"date": date, "unique_customers": len(customers)}
            for date, customers in daily_customers.items()
        ],
        key=lambda x: x["date"],
    )

    return {
        "total_units": total_units,
        "breakdown": breakdown,
        "price_per_unit": config.price_per_unit,
        "currency": config.currency,
        "item_code": config.billing_item,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Apply to invoice
# ─────────────────────────────────────────────────────────────────────────────


@frappe.whitelist()
def apply_usage_to_invoice(invoice_name, billing_month):
    """Fetch usage and apply it to the Sales Invoice.

    Actions performed (all via ``frappe.db`` / ``doc.save``):
    - Finds the invoice items row matching ``wb_config.billing_item``;
      creates one if absent.
    - Sets ``qty = total_units`` and ``rate = price_per_unit`` on that row.
    - Updates ``wb_total_units`` and ``wb_last_fetched`` on the invoice.
    - Creates or updates a ``WhatsApp Usage Log`` record.
    - Links ``wb_usage_log`` on the invoice.
    - Saves the invoice (docstatus stays 0 — does **not** submit).

    Returns
    -------
    dict
        ``{success, total_units, total_amount, price_per_unit, currency,
           breakdown, item_row_name, usage_log}``
    """
    # ── Get usage data ───────────────────────────────────────────────────────
    usage = get_usage(invoice_name, billing_month)

    total_units = usage["total_units"]
    price_per_unit = usage["price_per_unit"]
    item_code = usage["item_code"]
    breakdown = usage["breakdown"]
    currency = usage.get("currency")
    total_amount = total_units * price_per_unit

    # ── Load invoice and config ──────────────────────────────────────────────
    invoice = frappe.get_doc("Sales Invoice", invoice_name)

    if invoice.docstatus != 0:
        frappe.throw(
            "Cannot modify a submitted or cancelled invoice.",
            title="Invoice Not Editable",
        )

    config = frappe.get_doc("WhatsApp Billing Config", invoice.wb_config)

    # ── Update or append the billing item row ───────────────────────────────
    item_row_name = None
    billing_row_found = False

    for item in invoice.items:
        if item.item_code == item_code:
            item.qty = total_units
            item.rate = price_per_unit
            item_row_name = item.name
            billing_row_found = True
            break

    if not billing_row_found:
        new_row = invoice.append(
            "items",
            {
                "item_code": item_code,
                "qty": total_units,
                "rate": price_per_unit,
            },
        )
        # name is assigned after save; keep reference via object
        _new_row_ref = new_row

    # ── Update invoice custom fields ────────────────────────────────────────
    invoice.wb_total_units = total_units
    invoice.wb_last_fetched = frappe.utils.now_datetime()

    # ── Create or update WhatsApp Usage Log ─────────────────────────────────
    raw_breakdown_json = json.dumps(breakdown, ensure_ascii=False)

    existing_log = frappe.db.get_value(
        "WhatsApp Usage Log",
        {"sales_invoice": invoice_name, "billing_month": billing_month},
        "name",
    )

    if existing_log:
        frappe.db.set_value(
            "WhatsApp Usage Log",
            existing_log,
            {
                "total_billable_units": total_units,
                "price_per_unit": price_per_unit,
                "total_amount": total_amount,
                "fetched_on": frappe.utils.now_datetime(),
                "raw_breakdown": raw_breakdown_json,
                "status": "Pending",
            },
        )
        log_name = existing_log
    else:
        log = frappe.get_doc(
            {
                "doctype": "WhatsApp Usage Log",
                "sales_invoice": invoice_name,
                "customer": invoice.customer,
                "billing_month": billing_month,
                "total_billable_units": total_units,
                "price_per_unit": price_per_unit,
                "total_amount": total_amount,
                "api_endpoint": config.api_endpoint,
                "fetched_on": frappe.utils.now_datetime(),
                "raw_breakdown": raw_breakdown_json,
                "status": "Pending",
            }
        )
        log.insert(ignore_permissions=True)
        log_name = log.name

    # ── Link the log back onto the invoice ───────────────────────────────────
    invoice.wb_usage_log = log_name

    # ── Save invoice (totals recalculated automatically by Frappe) ───────────
    invoice.save(ignore_permissions=True)
    frappe.db.commit()

    # Resolve item_row_name for newly appended row
    if not billing_row_found:
        for item in invoice.items:
            if item.item_code == item_code:
                item_row_name = item.name
                break

    return {
        "success": True,
        "total_units": total_units,
        "total_amount": total_amount,
        "price_per_unit": price_per_unit,
        "currency": currency,
        "breakdown": breakdown,
        "item_row_name": item_row_name,
        "usage_log": log_name,
    }
