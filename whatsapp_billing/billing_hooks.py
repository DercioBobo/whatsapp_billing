# Copyright (c) 2024, Your Company and contributors
# For license information, please see license.txt
"""
Sales Invoice doc-event handlers for WhatsApp Billing.

Registered in hooks.py under doc_events["Sales Invoice"].
All handlers guard on wb_enabled == 1, so normal invoices are never touched.
"""

from datetime import date

import frappe


def _previous_month() -> str:
    """Return YYYY-MM for the calendar month immediately before today."""
    today = date.today()
    if today.month == 1:
        return f"{today.year - 1}-12"
    return f"{today.year}-{today.month - 1:02d}"


def on_sales_invoice_after_insert(doc, method=None):
    """Auto-populate billing data when Auto Repeat creates a new draft invoice.

    Conditions that must ALL be true before anything runs:
      1. doc.wb_enabled == 1  — this is a WhatsApp Billing invoice
      2. doc.auto_repeat      — it was spawned by Auto Repeat, not created manually
      3. doc.wb_config        — a billing config is linked (copied from the template)

    If any condition is false the function returns immediately and the invoice
    is left completely untouched — exactly like any other normal invoice.
    """
    if not doc.get("wb_enabled"):
        return

    if not doc.get("auto_repeat"):
        # Manually created invoice — user will set things up themselves via the
        # "Fetch WhatsApp Usage" button. Do nothing.
        return

    if not doc.get("wb_config"):
        frappe.log_error(
            f"Invoice {doc.name} has wb_enabled=1 and was created by Auto Repeat "
            f"({doc.auto_repeat}) but has no wb_config set. Skipping auto-fetch.\n"
            "Set a Billing Config on the Auto Repeat template invoice.",
            "WhatsApp Billing — Missing Config",
        )
        return

    billing_month = _previous_month()

    # Persist the correct billing month before calling apply_usage_to_invoice,
    # because that function reads it back from the DB via frappe.get_doc.
    frappe.db.set_value("Sales Invoice", doc.name, "wb_billing_month", billing_month)

    try:
        from whatsapp_billing.api.billing import apply_usage_to_invoice

        apply_usage_to_invoice(doc.name, billing_month)
        # apply_usage_to_invoice saves the invoice, updates items, and creates
        # the Usage Log. The invoice stays in draft (docstatus=0).

    except Exception:
        # Log the error but do NOT raise — the invoice must remain accessible
        # in draft so the user can open it and click "Fetch WhatsApp Usage"
        # manually to retry.
        frappe.log_error(
            frappe.get_traceback(),
            f"WhatsApp Billing Auto-Fetch Failed — {doc.name} ({billing_month})",
        )
