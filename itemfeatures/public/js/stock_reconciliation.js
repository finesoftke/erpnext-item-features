
frappe.ui.form.on("Stock Reconciliation", {


	set_valuation_rate_and_qty: function (frm, cdt, cdn) {
		var d = frappe.model.get_doc(cdt, cdn);

		if (d.item_code && d.warehouse) {
			frappe.call({
				method: "erpnext.stock.doctype.stock_reconciliation.stock_reconciliation.get_stock_balance_for",
				args: {
					item_code: d.item_code,
					warehouse: d.warehouse,
					posting_date: frm.doc.posting_date,
					posting_time: frm.doc.posting_time,
					batch_no: d.batch_no,
					row: d,
					custom_feature: d.custom_feature,
				},
				callback: function (r) {
					const row = frappe.model.get_doc(cdt, cdn);
					if (!frm.doc.scan_mode) {
						frappe.model.set_value(cdt, cdn, "qty", r.message.qty);
					}
					frappe.model.set_value(cdt, cdn, "valuation_rate", r.message.rate);
					frappe.model.set_value(cdt, cdn, "current_qty", r.message.qty);
					frappe.model.set_value(cdt, cdn, "current_valuation_rate", r.message.rate);
					frappe.model.set_value(cdt, cdn, "current_amount", r.message.rate * r.message.qty);
					frappe.model.set_value(cdt, cdn, "amount", row.qty * row.valuation_rate);
					frappe.model.set_value(cdt, cdn, "current_serial_no", r.message.serial_nos);
					frappe.model.set_value(
						cdt,
						cdn,
						"use_serial_batch_fields",
						r.message.use_serial_batch_fields
					);

					if (frm.doc.purpose == "Stock Reconciliation" && !frm.doc.scan_mode) {
						frappe.model.set_value(cdt, cdn, "serial_no", r.message.serial_nos);
					}
				},
			});
		}
	},

});