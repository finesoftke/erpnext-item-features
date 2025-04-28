
frappe.ui.form.on("Stock Entry", {


	set_basic_rate: function (frm, cdt, cdn) {
		const item = locals[cdt][cdn];
		item.transfer_qty = flt(item.qty) * flt(item.conversion_factor);

		const args = {
			item_code: item.item_code,
			posting_date: frm.doc.posting_date,
			posting_time: frm.doc.posting_time,
			warehouse: cstr(item.s_warehouse) || cstr(item.t_warehouse),
			serial_no: item.serial_no,
			batch_no: item.batch_no,
			company: frm.doc.company,
			qty: item.s_warehouse ? -1 * flt(item.transfer_qty) : flt(item.transfer_qty),
			voucher_type: frm.doc.doctype,
			voucher_no: item.name,
			allow_zero_valuation: 1,
			custom_feature: item.custom_feature,
		};

		if (item.item_code || item.serial_no) {
			frappe.call({
				method: "erpnext.stock.utils.get_incoming_rate",
				args: {
					args: args,
				},
				callback: function (r) {
					frappe.model.set_value(cdt, cdn, "basic_rate", r.message || 0.0);
					frm.events.calculate_basic_amount(frm, item);
				},
			});
		}
	},

	custom_feature(frm, cdt, cdn) {
		frm.events.set_basic_rate(frm, cdt, cdn);
	},

});