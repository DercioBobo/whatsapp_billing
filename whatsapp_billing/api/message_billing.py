# Copyright (c) 2024, Your Company and contributors
# For license information, please see license.txt
"""
WhatsApp Message Billing API
=============================
Exposes whitelisted endpoints called from the Sales Invoice client script.

Billing logic
-------------
  - Each customer's API endpoint reports daily message counts across all of
    their phone numbers/groups (fields: day, name, phone_number,
    total_mensagens_in_day).
  - Billable quantity ("total_messages") = SUM over every record in the
    billing month of (total_mensagens_in_day × member_count), where
    member_count comes from the config's manually maintained Group Member
    Count table (WhatsApp Message Group Member Count) and defaults to 1 for
    any phone_number not listed there — this is how billing "per message ×
    group members" is achieved without the API exposing group membership.
  - total_amount = total_messages × price_per_message
"""

import calendar
import json
from collections import defaultdict
from datetime import datetime

import frappe
import requests


# ─────────────────────────────────────────────────────────────────────────────
# Description template renderer
# ─────────────────────────────────────────────────────────────────────────────


def _render_description(
    template: str,
    billing_month: str,
    total_messages: int,
    price_per_message: float,
    total_amount: float,
    currency: str,
    customer_name: str,
) -> str:
    """Render the line description template with billing context variables.

    Supported variables
    -------------------
    {month_name}         Full month name in English, e.g. "February"
    {month_name_short}   Abbreviated month name, e.g. "Feb"
    {month}              Zero-padded month number, e.g. "02"
    {year}               Four-digit year, e.g. "2026"
    {billing_month}      YYYY-MM string, e.g. "2026-02"
    {total_messages}     Thousands-formatted message count, e.g. "1,234"
    {total_messages_raw} Plain integer string, e.g. "1234"
    {price_per_message}  Rate formatted to 2 decimal places, e.g. "10.00"
    {total_amount}       Amount formatted to 2 decimal places, e.g. "12,340.00"
    {currency}           Currency code, e.g. "MZN"
    {customer_name}      Customer full name as in ERPNext

    If the template contains an unrecognised variable, it is left as-is
    so the user can see exactly what went wrong rather than getting an error.
    """
    if not template:
        return ""

    try:
        year_str, month_str = billing_month.split("-")
        month_int = int(month_str)
    except (ValueError, AttributeError):
        return template

    context = {
        "month_name": calendar.month_name[month_int],        # "February"
        "month_name_short": calendar.month_abbr[month_int],  # "Feb"
        "month": month_str,                                   # "02"
        "year": year_str,                                     # "2026"
        "billing_month": billing_month,                       # "2026-02"
        "total_messages": f"{total_messages:,}",              # "1,234"
        "total_messages_raw": str(total_messages),            # "1234"
        "price_per_message": f"{price_per_message:,.2f}",     # "10.00"
        "total_amount": f"{total_amount:,.2f}",               # "12,340.00"
        "currency": currency or "",
        "customer_name": customer_name or "",
    }

    # Use format_map so unknown keys are left as literal {key} strings
    # instead of raising a KeyError.
    class _SafeDict(dict):
        def __missing__(self, key):
            return "{" + key + "}"

    return template.format_map(_SafeDict(context))


def _build_member_count_lookup(config) -> dict:
    """Return {phone_number: member_count} from the config's manually
    maintained Group Member Counts table.

    Any phone_number not listed here — including every individual contact —
    is treated as reaching 1 recipient per message when this lookup is used.
    """
    return {
        row.phone_number: row.member_count or 1
        for row in (config.get("member_counts") or [])
        if row.phone_number
    }


# ─────────────────────────────────────────────────────────────────────────────
# Public helpers
# ─────────────────────────────────────────────────────────────────────────────


@frappe.whitelist()
def get_config_for_customer(customer):
    """Return the active WhatsApp Message Billing Config for *customer*, or None.

    Used by the client script to auto-populate ``wmb_config`` when
    ``wmb_enabled`` is toggled on or the customer changes.
    """
    if not customer:
        return None

    config = frappe.db.get_value(
        "WhatsApp Message Billing Config",
        {"customer": customer, "is_active": 1},
        ["name", "price_per_message", "currency", "billing_item"],
        as_dict=True,
    )
    return config


@frappe.whitelist()
def test_connection(config_name):
    """Ping the API endpoint and return a diagnostics dict.

    Never raises — always returns a structured result so the client
    can decide how to display it.

    Returns
    -------
    dict
        success        bool
        total_records  int   — total items in the response array
        months         list  — unique YYYY-MM values found in the data
        sample         dict  — first record (sanitised), for visual confirmation
        error          str   — human-readable error message (when success=False)
        status_code    int   — HTTP status code (when available)
    """
    config = frappe.get_doc("WhatsApp Message Billing Config", config_name)

    headers = {"Accept": "application/json"}
    if config.get("api_token"):
        headers["Authorization"] = f"Bearer {config.get_password('api_token')}"

    try:
        response = requests.get(config.api_endpoint, headers=headers, timeout=30)
    except requests.exceptions.Timeout:
        return {"success": False, "error": "Connection timed out after 30 s. Check the endpoint URL and network access."}
    except requests.exceptions.ConnectionError:
        return {"success": False, "error": f"Could not connect to {config.api_endpoint}. Check the URL and DNS."}
    except Exception as exc:
        return {"success": False, "error": str(exc)}

    if not response.ok:
        msg = {
            401: "Unauthorized (401) — API token is missing or invalid.",
            403: "Forbidden (403) — token does not have access to this endpoint.",
            404: "Not Found (404) — the endpoint URL does not exist.",
            500: "Server Error (500) — the API server returned an internal error.",
        }.get(response.status_code, f"HTTP {response.status_code} — {response.reason}")
        return {"success": False, "error": msg, "status_code": response.status_code}

    try:
        raw = response.json()
    except Exception:
        return {"success": False, "error": "Response is not valid JSON. Check the endpoint returns application/json."}

    # Normalise to list
    if isinstance(raw, dict):
        for key in ("data", "results", "records", "items"):
            if key in raw and isinstance(raw[key], list):
                raw = raw[key]
                break
        else:
            raw = [raw]

    if not isinstance(raw, list):
        return {"success": False, "error": "Expected a JSON array but got something else."}

    # Collect unique months present in the data
    months = set()
    for record in raw:
        day_str = str(record.get("day", "")).strip()
        if day_str:
            try:
                months.add(datetime.strptime(day_str[:10], "%Y-%m-%d").strftime("%Y-%m"))
            except ValueError:
                pass

    return {
        "success": True,
        "total_records": len(raw),
        "months": sorted(months, reverse=True),
        "sample": raw[0] if raw else None,
        "status_code": response.status_code,
    }


@frappe.whitelist()
def list_phone_numbers(config_name):
    """Fetch the customer's API and return every distinct phone_number/group
    JID seen, with its most recent label and total message count.

    A convenience lookup for filling in Group Member Counts without having
    to copy exact phone_number/JID strings out of raw API output by hand —
    a typo there would silently bill that number as 1 recipient.

    Returns
    -------
    list[dict]
        Sorted by total_messages descending:
        ``[{phone_number, label, total_messages, is_group}]``
    """
    config = frappe.get_doc("WhatsApp Message Billing Config", config_name)

    if not config.api_endpoint:
        frappe.throw(
            "Set the API Endpoint before fetching phone numbers.",
            title="Missing API Endpoint",
        )

    headers = {"Accept": "application/json"}
    if config.get("api_token"):
        headers["Authorization"] = f"Bearer {config.get_password('api_token')}"

    try:
        response = requests.get(config.api_endpoint, headers=headers, timeout=30)
        response.raise_for_status()
        raw_data = response.json()
    except requests.exceptions.Timeout:
        frappe.throw("API request timed out (30 s). Check the endpoint or try again.", title="API Timeout")
    except requests.exceptions.ConnectionError as exc:
        frappe.throw(f"Could not connect to API endpoint: {config.api_endpoint}\n{exc}", title="Connection Error")
    except requests.exceptions.HTTPError as exc:
        frappe.throw(f"API returned an error: {exc}", title="API HTTP Error")
    except Exception as exc:
        frappe.throw(f"Unexpected error while fetching API data: {exc}", title="API Error")

    if isinstance(raw_data, dict):
        for key in ("data", "results", "records", "items"):
            if key in raw_data and isinstance(raw_data[key], list):
                raw_data = raw_data[key]
                break
        else:
            raw_data = [raw_data]

    if not isinstance(raw_data, list):
        frappe.throw("Unexpected API response format — expected a JSON array.", title="API Format Error")

    totals: dict = defaultdict(int)
    labels: dict = {}

    for record in raw_data:
        if not isinstance(record, dict):
            continue

        phone_number = record.get("phone_number")
        if not phone_number:
            continue

        totals[phone_number] += int(record.get("total_mensagens_in_day") or 0)

        name = str(record.get("name") or "").strip()
        if name:
            labels[phone_number] = name

    results = [
        {
            "phone_number": phone_number,
            "label": labels.get(phone_number, ""),
            "total_messages": total,
            "is_group": phone_number.endswith("@g.us"),
        }
        for phone_number, total in totals.items()
    ]
    results.sort(key=lambda r: r["total_messages"], reverse=True)
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Core billing logic
# ─────────────────────────────────────────────────────────────────────────────


@frappe.whitelist()
def get_message_usage(invoice_name, billing_month):
    """Fetch and calculate message usage from the external API.

    Does **not** modify any document — purely reads and computes.

    Parameters
    ----------
    invoice_name : str
        Name of the Sales Invoice that has ``wmb_enabled = 1``.
    billing_month : str
        Target month in ``YYYY-MM`` format.

    Returns
    -------
    dict
        ``{total_messages, breakdown, price_per_message, currency, item_code,
           unknown_phone_numbers}``. ``total_messages`` is reach-adjusted —
           each record's ``total_mensagens_in_day`` is multiplied by that
           phone_number/group's configured member count (default 1).
           ``unknown_phone_numbers`` lists any phone_number seen this month
           that has no Group Member Count row on the config (billed as 1).
    """
    invoice = frappe.get_doc("Sales Invoice", invoice_name)

    # ── Guard clauses ────────────────────────────────────────────────────────
    if not invoice.get("wmb_enabled"):
        frappe.throw(
            f"Invoice {invoice_name} does not have WhatsApp Message Billing enabled.",
            title="Not a WhatsApp Message Billing Invoice",
        )

    if not invoice.get("wmb_config"):
        frappe.throw(
            "Please set the Message Billing Config on the invoice before fetching usage.",
            title="Missing Billing Config",
        )

    config = frappe.get_doc("WhatsApp Message Billing Config", invoice.wmb_config)

    if not config.is_active:
        frappe.throw(
            f"Message Billing Config '{config.name}' is inactive. Activate it before billing.",
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

    # ── Filter to billing_month and sum reach (messages × members) per day ──
    # No customer_id filtering — the endpoint is already scoped to this one
    # customer, and every phone_number/group they send from counts towards
    # their bill. Each record's message count is multiplied by that
    # phone_number's configured member count (1 if not listed).
    member_counts = _build_member_count_lookup(config)
    daily_messages: dict = defaultdict(int)
    unknown_phone_numbers: set = set()

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

        phone_number = record.get("phone_number")
        member_count = member_counts.get(phone_number, 1)
        if phone_number not in member_counts:
            unknown_phone_numbers.add(phone_number)

        date_key = record_date.strftime("%Y-%m-%d")
        daily_messages[date_key] += int(record.get("total_mensagens_in_day") or 0) * member_count

    total_messages = sum(daily_messages.values())

    # ── Build sorted daily breakdown ─────────────────────────────────────────
    breakdown = sorted(
        [{"date": date, "messages": count} for date, count in daily_messages.items()],
        key=lambda x: x["date"],
    )

    return {
        "total_messages": total_messages,
        "breakdown": breakdown,
        "price_per_message": config.price_per_message,
        "currency": config.currency,
        "item_code": config.billing_item,
        "unknown_phone_numbers": sorted(n for n in unknown_phone_numbers if n),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Apply to invoice
# ─────────────────────────────────────────────────────────────────────────────


@frappe.whitelist()
def apply_message_usage_to_invoice(invoice_name, billing_month):
    """Fetch message usage and apply it to the Sales Invoice.

    Actions performed (all via ``frappe.db`` / ``doc.save``):
    - Finds the invoice items row matching ``wmb_config.billing_item``;
      creates one if absent.
    - Sets ``qty = total_messages`` and ``rate = price_per_message`` on that row.
    - Updates ``wmb_total_messages`` and ``wmb_last_fetched`` on the invoice.
    - Creates or updates a ``WhatsApp Message Usage Log`` record.
    - Links ``wmb_usage_log`` on the invoice.
    - Saves the invoice (docstatus stays 0 — does **not** submit).

    Returns
    -------
    dict
        ``{success, total_messages, total_amount, price_per_message, currency,
           breakdown, item_row_name, usage_log, unknown_phone_numbers}``
    """
    # ── Get usage data ───────────────────────────────────────────────────────
    usage = get_message_usage(invoice_name, billing_month)

    total_messages = usage["total_messages"]
    price_per_message = usage["price_per_message"]
    item_code = usage["item_code"]
    breakdown = usage["breakdown"]
    currency = usage.get("currency")
    unknown_phone_numbers = usage.get("unknown_phone_numbers") or []
    total_amount = total_messages * price_per_message

    # ── Load invoice and config ──────────────────────────────────────────────
    invoice = frappe.get_doc("Sales Invoice", invoice_name)

    if invoice.docstatus != 0:
        frappe.throw(
            "Cannot modify a submitted or cancelled invoice.",
            title="Invoice Not Editable",
        )

    config = frappe.get_doc("WhatsApp Message Billing Config", invoice.wmb_config)

    # ── Render line description (only if a template is configured) ───────────
    line_description = _render_description(
        template=config.get("line_description_template") or "",
        billing_month=billing_month,
        total_messages=total_messages,
        price_per_message=price_per_message,
        total_amount=total_amount,
        currency=config.currency or "",
        customer_name=invoice.customer_name or invoice.customer,
    )

    # ── Update or append the billing item row ───────────────────────────────
    # Only this specific row is touched. All other rows (e.g. the wb_config
    # billing row or Service Maintenance) are left exactly as they are.
    item_row_name = None
    billing_row_found = False

    for item in invoice.items:
        if item.item_code == item_code:
            item.qty = total_messages
            item.rate = price_per_message
            if line_description:
                item.description = line_description
            item_row_name = item.name
            billing_row_found = True
            break

    if not billing_row_found:
        new_row = invoice.append(
            "items",
            {
                "item_code": item_code,
                "qty": total_messages,
                "rate": price_per_message,
                "description": line_description or None,
            },
        )
        # name is assigned after save; keep reference via object
        _new_row_ref = new_row

    # ── Update invoice custom fields ────────────────────────────────────────
    invoice.wmb_billing_month = billing_month
    invoice.wmb_total_messages = total_messages
    invoice.wmb_last_fetched = frappe.utils.now_datetime()

    # ── Create or update WhatsApp Message Usage Log ─────────────────────────
    raw_breakdown_json = json.dumps(breakdown, ensure_ascii=False)

    existing_log = frappe.db.get_value(
        "WhatsApp Message Usage Log",
        {"sales_invoice": invoice_name, "billing_month": billing_month},
        "name",
    )

    if existing_log:
        frappe.db.set_value(
            "WhatsApp Message Usage Log",
            existing_log,
            {
                "total_messages": total_messages,
                "price_per_message": price_per_message,
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
                "doctype": "WhatsApp Message Usage Log",
                "sales_invoice": invoice_name,
                "customer": invoice.customer,
                "billing_month": billing_month,
                "total_messages": total_messages,
                "price_per_message": price_per_message,
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
    invoice.wmb_usage_log = log_name

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
        "total_messages": total_messages,
        "total_amount": total_amount,
        "price_per_message": price_per_message,
        "currency": currency,
        "breakdown": breakdown,
        "item_row_name": item_row_name,
        "usage_log": log_name,
        "unknown_phone_numbers": unknown_phone_numbers,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Manual reconciliation
# ─────────────────────────────────────────────────────────────────────────────


@frappe.whitelist()
def mark_message_usage_as_billed(customer, billing_month, sales_invoice):
    """Manually attest that *customer*'s message usage for *billing_month* was
    already billed via *sales_invoice*, without fetching or recalculating anything.

    Covers the case where an invoice was created by hand (the normal fetch was
    missed or skipped) — this only links/creates the WhatsApp Message Usage Log
    for that month and marks it Confirmed, so the Live Usage and Reconciliation
    reports stop flagging it. It never touches the invoice's items, totals, or
    any of its ``wmb_*`` fields.

    Returns
    -------
    dict
        ``{success, usage_log}``
    """
    if not frappe.db.exists("Sales Invoice", sales_invoice):
        frappe.throw(f"Sales Invoice {sales_invoice} does not exist.", title="Invoice Not Found")

    invoice_customer = frappe.db.get_value("Sales Invoice", sales_invoice, "customer")
    if invoice_customer != customer:
        frappe.throw(
            f"Sales Invoice {sales_invoice} belongs to customer '{invoice_customer}', not '{customer}'.",
            title="Customer Mismatch",
        )

    existing_log = frappe.db.get_value(
        "WhatsApp Message Usage Log",
        {"customer": customer, "billing_month": billing_month},
        "name",
    )

    if existing_log:
        frappe.db.set_value(
            "WhatsApp Message Usage Log",
            existing_log,
            {"sales_invoice": sales_invoice, "status": "Confirmed"},
        )
        log_name = existing_log
    else:
        config_endpoint = frappe.db.get_value(
            "WhatsApp Message Billing Config",
            {"customer": customer, "is_active": 1},
            "api_endpoint",
        )
        log = frappe.get_doc(
            {
                "doctype": "WhatsApp Message Usage Log",
                "sales_invoice": sales_invoice,
                "customer": customer,
                "billing_month": billing_month,
                "total_messages": 0,
                "price_per_message": 0,
                "api_endpoint": config_endpoint or "",
                "fetched_on": frappe.utils.now_datetime(),
                "status": "Confirmed",
            }
        )
        log.insert(ignore_permissions=True)
        log_name = log.name

    frappe.db.commit()

    return {"success": True, "usage_log": log_name}
