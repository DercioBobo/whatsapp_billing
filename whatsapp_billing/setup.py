"""
Installation hooks for whatsapp_billing.
Called by hooks.py: after_install = "whatsapp_billing.setup.after_install"
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


CUSTOM_FIELDS = {
    "Sales Invoice": [
        {
            "fieldname": "wb_section_break",
            "fieldtype": "Section Break",
            "label": "WhatsApp Billing",
            "insert_after": "remarks",
            "collapsible": 1,
        },
        {
            "fieldname": "wb_enabled",
            "fieldtype": "Check",
            "label": "WhatsApp Billing Invoice",
            "insert_after": "wb_section_break",
            "description": "When checked, this invoice is managed by the WhatsApp Billing app.",
        },
        {
            "fieldname": "wb_config",
            "fieldtype": "Link",
            "label": "Billing Config",
            "insert_after": "wb_enabled",
            "options": "WhatsApp Billing Config",
            "depends_on": "eval:doc.wb_enabled == 1",
            "get_query": "() => { return { filters: { customer: frm.doc.customer } }; }",
        },
        {
            "fieldname": "wb_billing_month",
            "fieldtype": "Data",
            "label": "Billing Month (YYYY-MM)",
            "insert_after": "wb_config",
            "depends_on": "eval:doc.wb_enabled == 1",
            "description": "Format: YYYY-MM, e.g. 2026-02",
        },
        {
            "fieldname": "wb_col_break",
            "fieldtype": "Column Break",
            "insert_after": "wb_billing_month",
        },
        {
            "fieldname": "wb_total_units",
            "fieldtype": "Int",
            "label": "Billable Units",
            "insert_after": "wb_col_break",
            "depends_on": "eval:doc.wb_enabled == 1",
            "read_only": 1,
        },
        {
            "fieldname": "wb_last_fetched",
            "fieldtype": "Datetime",
            "label": "Last Fetched",
            "insert_after": "wb_total_units",
            "depends_on": "eval:doc.wb_enabled == 1",
            "read_only": 1,
        },
        {
            "fieldname": "wb_usage_log",
            "fieldtype": "Link",
            "label": "Usage Log",
            "insert_after": "wb_last_fetched",
            "options": "WhatsApp Usage Log",
            "depends_on": "eval:doc.wb_enabled == 1",
            "read_only": 1,
        },
        {
            "fieldname": "wmb_section_break",
            "fieldtype": "Section Break",
            "label": "WhatsApp Message Billing",
            "insert_after": "wb_usage_log",
            "collapsible": 1,
        },
        {
            "fieldname": "wmb_enabled",
            "fieldtype": "Check",
            "label": "WhatsApp Message Billing Invoice",
            "insert_after": "wmb_section_break",
            "description": "When checked, this invoice is managed by the WhatsApp Message Billing app.",
        },
        {
            "fieldname": "wmb_config",
            "fieldtype": "Link",
            "label": "Message Billing Config",
            "insert_after": "wmb_enabled",
            "options": "WhatsApp Message Billing Config",
            "depends_on": "eval:doc.wmb_enabled == 1",
            "get_query": "() => { return { filters: { customer: frm.doc.customer } }; }",
        },
        {
            "fieldname": "wmb_billing_month",
            "fieldtype": "Data",
            "label": "Billing Month (YYYY-MM)",
            "insert_after": "wmb_config",
            "depends_on": "eval:doc.wmb_enabled == 1",
            "description": "Format: YYYY-MM, e.g. 2026-02",
        },
        {
            "fieldname": "wmb_col_break",
            "fieldtype": "Column Break",
            "insert_after": "wmb_billing_month",
        },
        {
            "fieldname": "wmb_total_messages",
            "fieldtype": "Int",
            "label": "Billable Messages",
            "insert_after": "wmb_col_break",
            "depends_on": "eval:doc.wmb_enabled == 1",
            "read_only": 1,
        },
        {
            "fieldname": "wmb_last_fetched",
            "fieldtype": "Datetime",
            "label": "Last Fetched",
            "insert_after": "wmb_total_messages",
            "depends_on": "eval:doc.wmb_enabled == 1",
            "read_only": 1,
        },
        {
            "fieldname": "wmb_usage_log",
            "fieldtype": "Link",
            "label": "Message Usage Log",
            "insert_after": "wmb_last_fetched",
            "options": "WhatsApp Message Usage Log",
            "depends_on": "eval:doc.wmb_enabled == 1",
            "read_only": 1,
        },
    ]
}


def after_install():
    """Create Sales Invoice custom fields on app installation."""
    create_custom_fields(CUSTOM_FIELDS, ignore_validate=True)
    frappe.db.commit()
    frappe.msgprint(
        "WhatsApp Billing: custom fields added to Sales Invoice.",
        alert=True,
        indicator="green",
    )
