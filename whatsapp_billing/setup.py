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
