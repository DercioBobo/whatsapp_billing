// Copyright (c) 2024, Your Company and contributors
// WhatsApp Billing — Sales Invoice client script
// Bundled via hooks.py: doctype_js = {"Sales Invoice": "public/js/sales_invoice.js"}

frappe.ui.form.on('Sales Invoice', {

	// ── Lifecycle ─────────────────────────────────────────────────────────────

	refresh: function (frm) {
		wb_setup_buttons(frm);
		wb_lock_fields_if_submitted(frm);
	},

	// ── Field events ──────────────────────────────────────────────────────────

	wb_enabled: function (frm) {
		if (!frm.doc.wb_enabled) return;

		// Auto-populate wb_config from customer
		if (frm.doc.customer) {
			wb_fetch_config(frm);
		}

		// Always set billing month to previous calendar month when enabling
		frm.set_value('wb_billing_month', wb_previous_month());
	},

	customer: function (frm) {
		if (frm.doc.wb_enabled && frm.doc.customer) {
			wb_fetch_config(frm);
		}
	},

	wb_config: function (frm) {
		if (!frm.doc.wb_config || !frm.doc.customer) return;

		// Validate config belongs to the current customer
		frappe.db.get_value(
			'WhatsApp Billing Config',
			frm.doc.wb_config,
			'customer',
			function (value) {
				if (value && value.customer && value.customer !== frm.doc.customer) {
					frappe.msgprint({
						title: __('Warning'),
						message: __(
							'The selected Billing Config (<b>{0}</b>) belongs to customer <b>{1}</b>, '
							+ 'not <b>{2}</b>. Please choose the correct config.',
							[frm.doc.wb_config, value.customer, frm.doc.customer]
						),
						indicator: 'orange',
					});
				}
			}
		);
	},
});

// ─────────────────────────────────────────────────────────────────────────────
// Button setup
// ─────────────────────────────────────────────────────────────────────────────

function wb_setup_buttons(frm) {
	// Remove stale buttons so refresh is idempotent
	frm.remove_custom_button(__('Fetch WhatsApp Usage'));
	frm.remove_custom_button(__('View Usage Log'));

	if (frm.doc.wb_enabled && frm.doc.docstatus === 0) {
		frm.add_custom_button(__('Fetch WhatsApp Usage'), function () {
			wb_run_fetch(frm);
		}).addClass('btn-primary');
	}

	if (frm.doc.wb_usage_log) {
		frm.add_custom_button(__('View Usage Log'), function () {
			frappe.set_route('Form', 'WhatsApp Usage Log', frm.doc.wb_usage_log);
		});
	}
}

// ─────────────────────────────────────────────────────────────────────────────
// Lock custom fields on submitted / cancelled invoices
// ─────────────────────────────────────────────────────────────────────────────

function wb_lock_fields_if_submitted(frm) {
	if (frm.doc.docstatus === 0) return;

	var fields = [
		'wb_enabled', 'wb_config', 'wb_billing_month',
		'wb_total_units', 'wb_last_fetched', 'wb_usage_log',
	];
	fields.forEach(function (f) {
		frm.set_df_property(f, 'read_only', 1);
	});
}

// ─────────────────────────────────────────────────────────────────────────────
// Auto-populate Billing Config
// ─────────────────────────────────────────────────────────────────────────────

function wb_fetch_config(frm) {
	frappe.call({
		method: 'whatsapp_billing.api.billing.get_config_for_customer',
		args: { customer: frm.doc.customer },
		callback: function (r) {
			if (r.message && r.message.name) {
				frm.set_value('wb_config', r.message.name);
			} else if (frm.doc.wb_config) {
				// Customer changed; clear stale config
				frm.set_value('wb_config', '');
			}
		},
	});
}

// ─────────────────────────────────────────────────────────────────────────────
// Previous calendar month as YYYY-MM
// ─────────────────────────────────────────────────────────────────────────────

function wb_previous_month() {
	var now = new Date();
	var prev = new Date(now.getFullYear(), now.getMonth() - 1, 1);
	var yyyy = prev.getFullYear();
	var mm = String(prev.getMonth() + 1).padStart(2, '0');
	return yyyy + '-' + mm;
}

// ─────────────────────────────────────────────────────────────────────────────
// Main fetch action
// ─────────────────────────────────────────────────────────────────────────────

function wb_run_fetch(frm) {
	// ── Client-side validation ────────────────────────────────────────────────
	if (!frm.doc.wb_billing_month || !/^\d{4}-\d{2}$/.test(frm.doc.wb_billing_month)) {
		frappe.msgprint({
			title: __('Validation Error'),
			message: __('Please set a valid <b>Billing Month</b> in YYYY-MM format (e.g. 2026-02).'),
			indicator: 'red',
		});
		return;
	}

	if (!frm.doc.wb_config) {
		frappe.msgprint({
			title: __('Validation Error'),
			message: __('Please set the <b>Billing Config</b> before fetching usage.'),
			indicator: 'red',
		});
		return;
	}

	// ── Progress + API call ──────────────────────────────────────────────────
	frappe.show_progress(
		__('WhatsApp Billing'),
		0, 100,
		__('Contacting API for {0}…', [frm.doc.wb_billing_month])
	);

	frappe.call({
		method: 'whatsapp_billing.api.billing.apply_usage_to_invoice',
		args: {
			invoice_name: frm.doc.name,
			billing_month: frm.doc.wb_billing_month,
		},
		callback: function (r) {
			frappe.hide_progress();

			if (!r.message || !r.message.success) return;

			var data = r.message;

			// Reload the form so items table and totals reflect server state
			frm.reload_doc();

			// ── Show breakdown dialog ────────────────────────────────────────
			wb_show_breakdown_dialog(data);
		},
		error: function () {
			frappe.hide_progress();
		},
	});
}

// ─────────────────────────────────────────────────────────────────────────────
// Breakdown confirmation dialog
// ─────────────────────────────────────────────────────────────────────────────

function wb_show_breakdown_dialog(data) {
	var breakdown = data.breakdown || [];
	var currency = data.currency || frappe.boot.sysdefaults.currency || '';

	var rows = breakdown.map(function (row) {
		return '<tr>'
			+ '<td style="padding:6px 14px;border-bottom:1px solid var(--border-color);">'
			+ row.date + '</td>'
			+ '<td style="padding:6px 14px;text-align:right;border-bottom:1px solid var(--border-color);">'
			+ frappe.utils.formatNumber(row.unique_customers, null, 0)
			+ '</td>'
			+ '</tr>';
	}).join('');

	// Total amount: use Frappe's format_currency if available
	var total_fmt;
	try {
		total_fmt = format_currency(data.total_amount, currency);
	} catch (e) {
		total_fmt = currency + ' ' + frappe.utils.formatNumber(data.total_amount, null, 2);
	}

	var table_html = '<div style="max-height:55vh;overflow-y:auto;margin-top:4px;">'
		+ '<table style="width:100%;border-collapse:collapse;font-size:13px;">'
		+ '<thead><tr style="background:var(--subtle-fg);">'
		+ '<th style="padding:8px 14px;text-align:left;border-bottom:2px solid var(--border-color);">'
		+ __('Date') + '</th>'
		+ '<th style="padding:8px 14px;text-align:right;border-bottom:2px solid var(--border-color);">'
		+ __('Unique End-Users') + '</th>'
		+ '</tr></thead>'
		+ '<tbody>' + rows + '</tbody>'
		+ '<tfoot>'
		+ '<tr style="font-weight:600;">'
		+ '<td style="padding:8px 14px;border-top:2px solid var(--border-color);">'
		+ __('Total Billable Units') + '</td>'
		+ '<td style="padding:8px 14px;text-align:right;border-top:2px solid var(--border-color);">'
		+ frappe.utils.formatNumber(data.total_units, null, 0)
		+ '</td>'
		+ '</tr>'
		+ '<tr style="font-weight:600;">'
		+ '<td style="padding:4px 14px;">' + __('Total Amount') + '</td>'
		+ '<td style="padding:4px 14px;text-align:right;">' + total_fmt + '</td>'
		+ '</tr>'
		+ '</tfoot>'
		+ '</table>'
		+ '</div>';

	var dialog = new frappe.ui.Dialog({
		title: __('WhatsApp Usage Applied'),
		fields: [
			{
				fieldtype: 'HTML',
				fieldname: 'breakdown_html',
				options: table_html,
			},
		],
		primary_action_label: __('Close'),
		primary_action: function () {
			dialog.hide();
		},
	});

	dialog.show();
}
