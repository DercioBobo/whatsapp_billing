// Copyright (c) 2024, Your Company and contributors
// For license information, please see license.txt

frappe.query_reports['WhatsApp Monthly Usage'] = {

	filters: [
		{
			fieldname: 'billing_month',
			label: __('Billing Month (YYYY-MM)'),
			fieldtype: 'Data',
			default: (function () {
				// Default to previous calendar month
				var now = new Date();
				var prev = new Date(now.getFullYear(), now.getMonth() - 1, 1);
				return prev.getFullYear() + '-' + String(prev.getMonth() + 1).padStart(2, '0');
			})(),
		},
		{
			fieldname: 'customer',
			label: __('Customer'),
			fieldtype: 'Link',
			options: 'Customer',
		},
		{
			fieldname: 'status',
			label: __('Log Status'),
			fieldtype: 'Select',
			options: '\nPending\nConfirmed\nCancelled',
		},
		{
			fieldname: 'invoice_status',
			label: __('Invoice Status'),
			fieldtype: 'Select',
			options: '\nDraft\nSubmitted\nCancelled',
		},
	],

	formatter: function (value, row, column, data, default_formatter) {
		// Let indicator-pill HTML pass through unescaped for status columns
		if (column.fieldname === 'invoice_status' || column.fieldname === 'status') {
			return value;
		}
		return default_formatter(value, row, column, data);
	},

	onload: function (report) {
		// "Submit All Drafts" convenience button — opens the list filtered to drafts
		report.page.add_inner_button(__('Open Draft Invoices'), function () {
			var month = frappe.query_report.get_filter_value('billing_month');
			var customer = frappe.query_report.get_filter_value('customer');

			var route_opts = { wb_enabled: 1, docstatus: 0 };
			if (month) route_opts['wb_billing_month'] = month;
			if (customer) route_opts['customer'] = customer;

			frappe.route_options = route_opts;
			frappe.set_route('List', 'Sales Invoice');
		});
	},
};
