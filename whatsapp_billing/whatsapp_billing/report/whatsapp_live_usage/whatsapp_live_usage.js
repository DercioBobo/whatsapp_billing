// Copyright (c) 2024, Your Company and contributors
// For license information, please see license.txt

frappe.query_reports['WhatsApp Live Usage'] = {

	// No default month — show ALL months available in the API so the user
	// can see the full history and spot any un-invoiced months at a glance.
	// Set the filter to narrow down to a specific month.
	filters: [
		{
			fieldname: 'customer',
			label: __('Customer'),
			fieldtype: 'Link',
			options: 'Customer',
		},
		{
			fieldname: 'billing_month',
			label: __('Billing Month (YYYY-MM)'),
			fieldtype: 'Data',
			description: __('Leave blank to see all months. Format: YYYY-MM'),
		},
	],

	formatter: function (value, row, column, data, default_formatter) {
		// Let indicator-pill HTML pass through unescaped
		if (column.fieldname === 'invoice_status') {
			return value;
		}
		return default_formatter(value, row, column, data);
	},

	onload: function (report) {
		// Refresh button label tweak to make it clear this hits the API
		report.page.set_title(__('WhatsApp Live Usage'));

		report.page.add_inner_button(__('Refresh from API'), function () {
			frappe.query_report.refresh();
		}, __('Actions'));
	},
};
