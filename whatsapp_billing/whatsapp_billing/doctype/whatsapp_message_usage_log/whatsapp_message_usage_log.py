# Copyright (c) 2024, Your Company and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class WhatsAppMessageUsageLog(Document):
    def validate(self):
        # total_messages / price_per_message are manually editable so a
        # log can be corrected during reconciliation; keep total_amount in sync.
        self.total_amount = (self.total_messages or 0) * (self.price_per_message or 0)

    def before_submit(self):
        frappe.throw("WhatsApp Message Usage Log cannot be submitted directly.")

    def on_cancel(self):
        self.status = "Cancelled"
