# Copyright (c) 2024, Your Company and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class WhatsAppUsageLog(Document):
    def validate(self):
        # total_billable_units / price_per_unit are manually editable so a
        # log can be corrected during reconciliation; keep total_amount in sync.
        self.total_amount = (self.total_billable_units or 0) * (self.price_per_unit or 0)

    def before_submit(self):
        frappe.throw("WhatsApp Usage Log cannot be submitted directly.")

    def on_cancel(self):
        self.status = "Cancelled"
