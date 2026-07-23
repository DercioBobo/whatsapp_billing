# Copyright (c) 2024, Your Company and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class WhatsAppMessageGroupMemberCount(Document):
    def validate(self):
        if not self.member_count or self.member_count < 1:
            frappe.throw(
                f"Member Count for '{self.phone_number}' must be at least 1.",
                title="Invalid Member Count",
            )
