// Copyright (c) 2024, Your Company and contributors
// For license information, please see license.txt

frappe.ui.form.on('WhatsApp Billing Config', {
	refresh: function (frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__('View Invoices'), function () {
				frappe.route_options = { wb_config: frm.doc.name };
				frappe.set_route('List', 'Sales Invoice');
			});
		}
	},

	customer: function (frm) {
		// When customer is set, filter billing_item by nothing special — keep it open
	},
});
