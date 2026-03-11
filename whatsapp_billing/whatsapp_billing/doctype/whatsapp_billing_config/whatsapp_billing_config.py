# Copyright (c) 2024, Your Company and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class WhatsAppBillingConfig(Document):
    def before_insert(self):
        if not self.currency:
            self.currency = frappe.defaults.get_global_default("currency")

    def validate(self):
        if not self.currency:
            self.currency = frappe.defaults.get_global_default("currency")

        # Enforce one active config per customer
        if self.is_active:
            existing = frappe.db.get_value(
                "WhatsApp Billing Config",
                {
                    "customer": self.customer,
                    "is_active": 1,
                    "name": ("!=", self.name),
                },
                "name",
            )
            if existing:
                frappe.throw(
                    f"Customer {self.customer} already has an active WhatsApp Billing Config: "
                    f"<b>{existing}</b>. Deactivate it before creating a new one.",
                    title="Duplicate Active Config",
                )
