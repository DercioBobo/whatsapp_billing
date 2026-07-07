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

	onload: function (report) {
		report.page.add_inner_button(__('Mark as Billed'), function () {
			wb_open_reconcile_dialog();
		}, __('Actions'));
	},
};

// ─────────────────────────────────────────────────────────────────────────────
// Mark as Billed — re-point a mismatched/superseded log at the correct
// invoice and mark it Confirmed, without touching units or amounts.
// ─────────────────────────────────────────────────────────────────────────────

function wb_open_reconcile_dialog() {
	var customer_filter = frappe.query_report.get_filter_value('customer');
	var month_filter = frappe.query_report.get_filter_value('billing_month');

	var dialog = new frappe.ui.Dialog({
		title: __('Mark Usage as Already Billed'),
		fields: [
			{
				fieldname: 'customer',
				label: __('Customer'),
				fieldtype: 'Link',
				options: 'Customer',
				reqd: 1,
				default: customer_filter || '',
			},
			{
				fieldname: 'billing_month',
				label: __('Billing Month (YYYY-MM)'),
				fieldtype: 'Data',
				description: __('Format: YYYY-MM, e.g. 2026-02'),
				reqd: 1,
				default: month_filter || '',
			},
			{
				fieldname: 'sales_invoice',
				label: __('Sales Invoice'),
				fieldtype: 'Link',
				options: 'Sales Invoice',
				reqd: 1,
				get_query: function () {
					var customer = dialog.get_value('customer');
					return customer ? { filters: { customer: customer } } : {};
				},
			},
		],
		primary_action_label: __('Mark as Billed'),
		primary_action: function (values) {
			if (!/^\d{4}-\d{2}$/.test(values.billing_month)) {
				frappe.msgprint({
					title: __('Validation Error'),
					message: __('Billing Month must be in YYYY-MM format, e.g. 2026-02.'),
					indicator: 'red',
				});
				return;
			}

			frappe.call({
				method: 'whatsapp_billing.api.billing.mark_usage_as_billed',
				args: values,
				callback: function (r) {
					if (!r.message || !r.message.success) return;
					dialog.hide();
					frappe.show_alert({ message: __('Marked as billed.'), indicator: 'green' });
					frappe.query_report.refresh();
				},
			});
		},
	});

	dialog.show();
}
