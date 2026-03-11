// Copyright (c) 2024, Your Company and contributors
// For license information, please see license.txt

frappe.ui.form.on('WhatsApp Usage Log', {
	refresh: function (frm) {
		if (frm.doc.sales_invoice) {
			frm.add_custom_button(__('Open Invoice'), function () {
				frappe.set_route('Form', 'Sales Invoice', frm.doc.sales_invoice);
			});
		}

		// Render breakdown JSON as a readable table
		if (frm.doc.raw_breakdown) {
			try {
				var breakdown = JSON.parse(frm.doc.raw_breakdown);
				var rows = breakdown.map(function (r) {
					return '<tr><td style="padding:5px 10px;">' + r.date + '</td>'
						+ '<td style="padding:5px 10px;text-align:right;">' + r.unique_customers + '</td></tr>';
				}).join('');

				var html = '<div style="margin-top:8px;">'
					+ '<table style="width:100%;border-collapse:collapse;font-size:13px;">'
					+ '<thead><tr style="border-bottom:2px solid var(--border-color);">'
					+ '<th style="padding:6px 10px;text-align:left;">Date</th>'
					+ '<th style="padding:6px 10px;text-align:right;">Unique Customers</th>'
					+ '</tr></thead><tbody>' + rows + '</tbody></table></div>';

				frm.set_df_property('raw_breakdown', 'description', html);
			} catch (e) {
				// Not valid JSON, leave as-is
			}
		}
	},
});
