// Copyright (c) 2024, Your Company and contributors
// For license information, please see license.txt

frappe.ui.form.on('WhatsApp Billing Config', {

	refresh: function (frm) {
		if (frm.is_new()) return;

		frm.add_custom_button(__('Test Connection'), function () {
			wb_test_connection(frm);
		}, __('Actions'));

		frm.add_custom_button(__('View Invoices'), function () {
			frappe.route_options = { wb_config: frm.doc.name };
			frappe.set_route('List', 'Sales Invoice');
		}, __('Actions'));
	},
});

// ─────────────────────────────────────────────────────────────────────────────

function wb_test_connection(frm) {
	frappe.show_progress(__('Testing Connection'), 0, 100, __('Contacting API…'));

	frappe.call({
		method: 'whatsapp_billing.api.billing.test_connection',
		args: { config_name: frm.doc.name },
		callback: function (r) {
			frappe.hide_progress();

			if (!r.message) return;
			var d = r.message;

			if (!d.success) {
				wb_show_result_dialog(false, frm.doc.customer, d.error, null);
				return;
			}

			wb_show_result_dialog(true, frm.doc.customer, null, d);
		},
		error: function () {
			frappe.hide_progress();
		},
	});
}

function wb_show_result_dialog(success, customer, error_msg, data) {
	var title = success ? __('Connection Successful') : __('Connection Failed');

	var body;
	if (!success) {
		body = `
			<div style="display:flex;align-items:flex-start;gap:12px;padding:8px 0;">
				<span class="indicator-pill red" style="margin-top:2px;flex-shrink:0;"></span>
				<div>
					<div style="font-weight:600;margin-bottom:4px;">${__('Could not reach the API')}</div>
					<div style="color:var(--text-muted);font-size:13px;">${frappe.utils.escape_html(error_msg)}</div>
				</div>
			</div>`;
	} else {
		// Months pills
		var month_pills = (data.months || []).map(function (m) {
			return `<span style="
				display:inline-block;padding:2px 8px;margin:2px;border-radius:10px;
				background:var(--bg-light-gray);font-size:12px;font-weight:500;">${m}</span>`;
		}).join('') || '<span style="color:var(--text-muted);">—</span>';

		// Sample record table
		var sample_rows = '';
		if (data.sample) {
			sample_rows = Object.entries(data.sample).map(function (kv) {
				return `<tr>
					<td style="padding:4px 10px;color:var(--text-muted);font-size:12px;white-space:nowrap;">${frappe.utils.escape_html(kv[0])}</td>
					<td style="padding:4px 10px;font-size:12px;">${frappe.utils.escape_html(String(kv[1]))}</td>
				</tr>`;
			}).join('');
		}

		body = `
			<div style="display:flex;align-items:center;gap:10px;padding:8px 0 16px;">
				<span class="indicator-pill green" style="flex-shrink:0;"></span>
				<span style="font-weight:600;font-size:14px;">
					${data.total_records.toLocaleString()} ${__('records received')}
				</span>
			</div>

			<div style="margin-bottom:14px;">
				<div style="font-size:11px;text-transform:uppercase;letter-spacing:.05em;
					color:var(--text-muted);margin-bottom:6px;">${__('Months in data')}</div>
				<div>${month_pills}</div>
			</div>

			${data.sample ? `
			<details style="border:1px solid var(--border-color);border-radius:6px;overflow:hidden;">
				<summary style="padding:8px 12px;cursor:pointer;font-size:12px;
					font-weight:600;background:var(--bg-light-gray);user-select:none;">
					${__('Sample record')}
				</summary>
				<table style="width:100%;border-collapse:collapse;">
					${sample_rows}
				</table>
			</details>` : ''}`;
	}

	var dialog = new frappe.ui.Dialog({
		title: title,
		fields: [{ fieldtype: 'HTML', fieldname: 'body', options: body }],
		primary_action_label: __('Close'),
		primary_action: function () { dialog.hide(); },
	});

	dialog.show();
}
