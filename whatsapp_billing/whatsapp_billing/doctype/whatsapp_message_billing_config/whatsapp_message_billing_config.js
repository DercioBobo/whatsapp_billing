// Copyright (c) 2024, Your Company and contributors
// For license information, please see license.txt

frappe.ui.form.on('WhatsApp Message Billing Config', {
	refresh: function (frm) {
		frm.remove_custom_button(__('Fetch Phone Numbers / Group JIDs'));

		if (frm.doc.api_endpoint) {
			frm.add_custom_button(__('Fetch Phone Numbers / Group JIDs'), function () {
				wmbc_fetch_phone_numbers(frm);
			});
		}
	},
});

// ─────────────────────────────────────────────────────────────────────────────
// Fetch + pick phone numbers / group JIDs from the live API
// ─────────────────────────────────────────────────────────────────────────────

function wmbc_fetch_phone_numbers(frm) {
	if (frm.is_dirty()) {
		frappe.msgprint({
			title: __('Save First'),
			message: __('Please save the config before fetching phone numbers, so the API Endpoint and Token are up to date.'),
			indicator: 'orange',
		});
		return;
	}

	frappe.call({
		method: 'whatsapp_billing.api.message_billing.list_phone_numbers',
		args: { config_name: frm.doc.name },
		freeze: true,
		freeze_message: __('Fetching phone numbers…'),
		callback: function (r) {
			var numbers = r.message || [];
			if (!numbers.length) {
				frappe.msgprint({
					title: __('No Data'),
					message: __('The API returned no records with a phone_number.'),
					indicator: 'orange',
				});
				return;
			}
			wmbc_show_picker_dialog(frm, numbers);
		},
	});
}

function wmbc_show_picker_dialog(frm, numbers) {
	var existing = {};
	(frm.doc.member_counts || []).forEach(function (row) {
		if (row.phone_number) existing[row.phone_number] = true;
	});

	var options = numbers.map(function (n) {
		var tag = n.is_group ? __('Group') : __('Contact');
		var label_part = n.label ? (n.label + ' — ') : '';
		var already = existing[n.phone_number] ? '  ✓ ' + __('already added') : '';
		return {
			label: label_part + n.phone_number + '  ·  ' + tag + '  ·  '
				+ frappe.utils.formatNumber(n.total_messages, null, 0) + ' ' + __('msgs seen') + already,
			value: n.phone_number,
			checked: 0,
		};
	});

	var dialog = new frappe.ui.Dialog({
		title: __('Select Phone Numbers / Group JIDs to Add'),
		fields: [
			{
				fieldtype: 'HTML',
				options: '<div style="font-size:12px;color:var(--text-muted);margin-bottom:8px;">'
					+ __('Sorted by messages seen, most active first. Selected numbers are added to Group Member Counts below with Member Count = 1 — edit the count on each actual group afterward.')
					+ '</div>',
			},
			{
				fieldtype: 'MultiCheck',
				fieldname: 'numbers',
				label: __('Phone Numbers / Group JIDs'),
				options: options,
				columns: 1,
			},
		],
		primary_action_label: __('Add Selected'),
		primary_action: function (values) {
			var selected = values.numbers || [];
			var added = 0;

			selected.forEach(function (phone_number) {
				if (existing[phone_number]) return; // already on the table — skip

				var meta = numbers.find(function (n) { return n.phone_number === phone_number; });
				var row = frm.add_child('member_counts');
				row.phone_number = phone_number;
				row.label = meta ? meta.label : '';
				row.member_count = 1;

				existing[phone_number] = true;
				added++;
			});

			frm.refresh_field('member_counts');
			dialog.hide();

			if (added) {
				frm.dirty();
				frappe.show_alert({
					message: __('{0} number(s) added — set the real Member Count for each group, then save.', [added]),
					indicator: 'green',
				});
			} else {
				frappe.show_alert({
					message: __('Nothing new to add — everything selected was already on the table.'),
					indicator: 'orange',
				});
			}
		},
	});

	dialog.show();
}
