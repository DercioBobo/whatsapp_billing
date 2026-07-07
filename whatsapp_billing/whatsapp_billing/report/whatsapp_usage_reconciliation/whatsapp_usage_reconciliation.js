// Copyright (c) 2024, Your Company and contributors
// For license information, please see license.txt

frappe.query_reports['WhatsApp Usage Reconciliation'] = {

	filters: [
		{
			fieldname: 'billing_month',
			label: __('Billing Month (YYYY-MM)'),
			fieldtype: 'Data',
		},
		{
			fieldname: 'customer',
			label: __('Customer'),
			fieldtype: 'Link',
			options: 'Customer',
		},
		{
			fieldname: 'mismatches_only',
			label: __('Only Show Mismatches'),
			fieldtype: 'Check',
			default: 1,
		},
	],

	formatter: function (value, row, column, data, default_formatter) {
		// Let indicator-pill HTML pass through unescaped for status columns
		if (['invoice_status', 'log_status', 'match_status'].includes(column.fieldname)) {
			return value;
		}
		return default_formatter(value, row, column, data);
	},
};
