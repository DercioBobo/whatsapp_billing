# Copyright (c) 2024, Your Company and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class WhatsAppUsageLog(Document):
    def before_submit(self):
        frappe.throw("WhatsApp Usage Log cannot be submitted directly.")

    def on_cancel(self):
        self.status = "Cancelled"
