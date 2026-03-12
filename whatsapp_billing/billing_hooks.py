# Copyright (c) 2024, Your Company and contributors
# For license information, please see license.txt
"""
Sales Invoice doc-event handlers for WhatsApp Billing.

Registered in hooks.py under doc_events["Sales Invoice"].
All handlers guard on wb_enabled == 1, so normal invoices are never touched.
"""

import traceback
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
        error_details = traceback.format_exc()

        # Always log to Error Log regardless of email config
        frappe.log_error(
            error_details,
            f"WhatsApp Billing Auto-Fetch Failed — {doc.name} ({billing_month})",
        )

        # Send notification email if configured on the billing config
        _notify_failure(doc, billing_month, error_details)


def _notify_failure(doc, billing_month, error_details):
    """Send a failure notification email if the config has one set.

    Uses the system's default outgoing email account (Email Account with
    default_outgoing = 1) as the sender — same as all other ERPNext emails.
    """
    try:
        config = frappe.db.get_value(
            "WhatsApp Billing Config",
            doc.wb_config,
            ["notification_email", "customer"],
            as_dict=True,
        )

        if not config or not config.notification_email:
            return

        invoice_url = frappe.utils.get_url_to_form("Sales Invoice", doc.name)
        customer_name = frappe.db.get_value("Customer", config.customer, "customer_name") or config.customer

        # Extract just the first line of the traceback for the subject
        first_error_line = next(
            (l.strip() for l in reversed(error_details.splitlines()) if l.strip()),
            "Unknown error",
        )

        subject = f"[WhatsApp Billing] Auto-fetch failed — {doc.name}"

        message = f"""
<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;color:#333;">

  <div style="background:#c0392b;padding:16px 24px;border-radius:6px 6px 0 0;">
    <h2 style="margin:0;color:#fff;font-size:18px;">
      WhatsApp Billing — Auto-fetch Failed
    </h2>
  </div>

  <div style="border:1px solid #ddd;border-top:none;padding:24px;border-radius:0 0 6px 6px;">

    <p style="margin:0 0 20px;">
      The automatic usage fetch that runs when Auto Repeat creates a new invoice
      has failed. The invoice is in <strong>Draft</strong> and needs to be populated manually.
    </p>

    <table style="width:100%;border-collapse:collapse;margin-bottom:24px;">
      <tr style="border-bottom:1px solid #eee;">
        <td style="padding:8px 0;color:#666;width:140px;">Customer</td>
        <td style="padding:8px 0;font-weight:600;">{frappe.utils.escape_html(customer_name)}</td>
      </tr>
      <tr style="border-bottom:1px solid #eee;">
        <td style="padding:8px 0;color:#666;">Invoice</td>
        <td style="padding:8px 0;">
          <a href="{invoice_url}" style="color:#2980b9;text-decoration:none;font-weight:600;">
            {frappe.utils.escape_html(doc.name)}
          </a>
        </td>
      </tr>
      <tr style="border-bottom:1px solid #eee;">
        <td style="padding:8px 0;color:#666;">Billing Month</td>
        <td style="padding:8px 0;">{frappe.utils.escape_html(billing_month)}</td>
      </tr>
      <tr>
        <td style="padding:8px 0;color:#666;">Error</td>
        <td style="padding:8px 0;color:#c0392b;font-family:monospace;font-size:13px;">
          {frappe.utils.escape_html(first_error_line)}
        </td>
      </tr>
    </table>

    <div style="margin-bottom:24px;">
      <a href="{invoice_url}"
         style="display:inline-block;padding:10px 20px;background:#2980b9;
                color:#fff;text-decoration:none;border-radius:4px;font-weight:600;">
        Open Invoice &rarr;
      </a>
    </div>

    <p style="margin:0;font-size:12px;color:#999;border-top:1px solid #eee;padding-top:16px;">
      Once the invoice is open, click <strong>Fetch WhatsApp Usage</strong> to retry.<br>
      The full error trace is available in ERPNext &rsaquo; Error Log.
    </p>

  </div>
</div>
"""

        frappe.sendmail(
            recipients=[config.notification_email],
            subject=subject,
            message=message,
            now=True,  # send immediately, do not queue
        )

    except Exception:
        # Email failure must never crash the hook — just log it
        frappe.log_error(
            traceback.format_exc(),
            f"WhatsApp Billing — Could not send failure notification for {doc.name}",
        )
