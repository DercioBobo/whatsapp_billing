app_name = "whatsapp_billing"
app_title = "WhatsApp Billing"
app_publisher = "Your Company"
app_description = "Automated WhatsApp/USSD session billing for ERPNext"
app_email = "info@example.com"
app_license = "MIT"

# Compatible with ERPNext v13, v14, v15
required_apps = []

# ─── JS bundles ────────────────────────────────────────────────────────────────
doctype_js = {
    "Sales Invoice": "public/js/sales_invoice.js"
}

# ─── Fixtures ──────────────────────────────────────────────────────────────────
# These are imported automatically on `bench migrate` after install.
# They define the custom fields added to Sales Invoice.
fixtures = [
    {
        "doctype": "Custom Field",
        "filters": [
            ["dt", "=", "Sales Invoice"],
            [
                "fieldname",
                "in",
                [
                    "wb_section_break",
                    "wb_enabled",
                    "wb_config",
                    "wb_billing_month",
                    "wb_col_break",
                    "wb_total_units",
                    "wb_last_fetched",
                    "wb_usage_log",
                ],
            ],
        ],
    }
]

# ─── Installation hook ─────────────────────────────────────────────────────────
after_install = "whatsapp_billing.setup.after_install"

# ─── Scheduler (intentionally empty — no auto-scheduling) ─────────────────────
scheduler_events = {}

# ─── Doc Events (intentionally empty — fully manual trigger) ──────────────────
doc_events = {}
