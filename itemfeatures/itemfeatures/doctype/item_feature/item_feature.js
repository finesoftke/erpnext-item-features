// Copyright (c) 2023, Finesoft Afrika and contributors
// For license information, please see license.txt

frappe.ui.form.on('Item Feature', {
	// refresh: function(frm) {

	// }
});

// erpnext.bom.FeatureController = class FeatureController extends erpnext.TransactionController {
// 	conversion_rate(doc) {
// 		if(this.frm.doc.currency === this.get_company_currency()) {
// 			this.frm.set_value("conversion_rate", 1.0);
// 		} else {
// 			erpnext.bom.update_cost(doc);
// 		}
// 	}

// 	item_code(doc, cdt, cdn){
// 		var scrap_items = false;
// 		var child = locals[cdt][cdn];
// 		if (child.doctype == 'BOM Scrap Item') {
// 			scrap_items = true;
// 		}

// 		if (child.bom_no) {
// 			child.bom_no = '';
// 		}

// 		get_bom_material_detail(doc, cdt, cdn, scrap_items);
// 	}

// 	buying_price_list(doc) {
// 		this.apply_price_list();
// 	}

// 	plc_conversion_rate(doc) {
// 		if (!this.in_apply_price_list) {
// 			this.apply_price_list(null, true);
// 		}
// 	}

// 	conversion_factor(doc, cdt, cdn) {
// 		if (frappe.meta.get_docfield(cdt, "stock_qty", cdn)) {
// 			var item = frappe.get_doc(cdt, cdn);
// 			frappe.model.round_floats_in(item, ["qty", "conversion_factor"]);
// 			item.stock_qty = flt(item.qty * item.conversion_factor, precision("stock_qty", item));
// 			refresh_field("stock_qty", item.name, item.parentfield);
// 			this.toggle_conversion_factor(item);
// 			this.frm.events.update_cost(this.frm);
// 		}
// 	}
// };

// extend_cscript(cur_frm.cscript, new erpnext.bom.FeatureController({frm: cur_frm}));

// cur_frm.cscript.hour_rate = function(doc) {
// 	erpnext.bom.calculate_op_cost(doc);
// 	erpnext.bom.calculate_total(doc);
// };

// cur_frm.cscript.time_in_mins = cur_frm.cscript.hour_rate;

// cur_frm.cscript.bom_no = function(doc, cdt, cdn) {
// 	get_bom_material_detail(doc, cdt, cdn, false);
// };

// cur_frm.cscript.is_default = function(doc) {
// 	if (doc.is_default) cur_frm.set_value("is_active", 1);
// };

// var get_bom_material_detail = function(doc, cdt, cdn, scrap_items) {
// 	if (!doc.company) {
// 		frappe.throw({message: __("Please select a Company first."), title: __("Mandatory")});
// 	}

// 	var d = locals[cdt][cdn];
// 	if (d.item_code) {
// 		return frappe.call({
// 			doc: doc,
// 			method: "get_bom_material_detail",
// 			args: {
// 				"company": doc.company,
// 				"item_code": d.item_code,
// 				"bom_no": d.bom_no != null ? d.bom_no: '',
// 				"scrap_items": scrap_items,
// 				"qty": d.qty,
// 				"stock_qty": d.stock_qty,
// 				"include_item_in_manufacturing": d.include_item_in_manufacturing,
// 				"uom": d.uom,
// 				"stock_uom": d.stock_uom,
// 				"conversion_factor": d.conversion_factor,
// 				"sourced_by_supplier": d.sourced_by_supplier,
// 				"do_not_explode": d.do_not_explode
// 			},
// 			callback: function(r) {
// 				d = locals[cdt][cdn];

// 				$.extend(d, r.message);
// 				refresh_field("items");
// 				refresh_field("scrap_items");

// 				doc = locals[doc.doctype][doc.name];
// 				erpnext.bom.calculate_rm_cost(doc);
// 			},
// 			freeze: true
// 		});
// 	}
// };

// cur_frm.cscript.qty = function(doc) {
// 	erpnext.bom.calculate_rm_cost(doc);
// };

// cur_frm.cscript.rate = function(doc, cdt, cdn) {
// 	var d = locals[cdt][cdn];
// 	const is_scrap_item = cdt == "BOM Scrap Item";

// 	if (d.bom_no) {
// 		frappe.msgprint(__("You cannot change the rate if BOM is mentioned against any Item."));
// 		get_bom_material_detail(doc, cdt, cdn, is_scrap_item);
// 	} else {
// 		erpnext.bom.calculate_rm_cost(doc);
// 		erpnext.bom.calculate_scrap_materials_cost(doc);
// 		erpnext.bom.calculate_total(doc);
// 	}
// };

// erpnext.bom.calculate_rm_cost = function(doc) {
// 	var rm = doc.items || [];
// 	var total_rm_cost = 0;
// 	var base_total_rm_cost = 0;
// 	for(var i=0;i<rm.length;i++) {
// 		var amount = flt(rm[i].rate) * flt(rm[i].qty);
// 		var base_amount = amount * flt(doc.conversion_rate);

// 		frappe.model.set_value('BOM Item', rm[i].name, 'base_rate',
// 			flt(rm[i].rate) * flt(doc.conversion_rate));
// 		frappe.model.set_value('BOM Item', rm[i].name, 'amount', amount);
// 		frappe.model.set_value('BOM Item', rm[i].name, 'base_amount', base_amount);
// 		frappe.model.set_value('BOM Item', rm[i].name,
// 			'qty_consumed_per_unit', flt(rm[i].stock_qty)/flt(doc.quantity));

// 		total_rm_cost += amount;
// 		base_total_rm_cost += base_amount;
// 	}
// 	cur_frm.set_value("raw_material_cost", total_rm_cost);
// };

// cur_frm.cscript.validate = function(doc) {
// 	erpnext.bom.calculate_rm_cost(doc);
// };

// frappe.ui.form.on("BOM Operation", "operation", function(frm, cdt, cdn) {
// 	var d = locals[cdt][cdn];

// 	if(!d.operation) return;

// 	frappe.call({
// 		"method": "frappe.client.get",
// 		args: {
// 			doctype: "Operation",
// 			name: d.operation
// 		},
// 		callback: function (data) {
// 			if(data.message.description) {
// 				frappe.model.set_value(d.doctype, d.name, "description", data.message.description);
// 			}
// 			if(data.message.workstation) {
// 				frappe.model.set_value(d.doctype, d.name, "workstation", data.message.workstation);
// 			}
// 		}
// 	});
// });

// frappe.ui.form.on("BOM Operation", "workstation", function(frm, cdt, cdn) {
// 	var d = locals[cdt][cdn];

// 	frappe.call({
// 		"method": "frappe.client.get",
// 		args: {
// 			doctype: "Workstation",
// 			name: d.workstation
// 		},
// 		callback: function (data) {
// 			frappe.model.set_value(d.doctype, d.name, "base_hour_rate", data.message.hour_rate);
// 			frappe.model.set_value(d.doctype, d.name, "hour_rate",
// 				flt(flt(data.message.hour_rate) / flt(frm.doc.conversion_rate)), 2);

// 			erpnext.bom.calculate_op_cost(frm.doc);
// 			erpnext.bom.calculate_total(frm.doc);
// 		}
// 	});
// });

// frappe.ui.form.on("BOM Item", {
// 	do_not_explode: function(frm, cdt, cdn) {
// 		get_bom_material_detail(frm.doc, cdt, cdn, false);
// 	}
// })


// frappe.ui.form.on("BOM Item", "qty", function(frm, cdt, cdn) {
// 	var d = locals[cdt][cdn];
// 	d.stock_qty = d.qty * d.conversion_factor;
// 	refresh_field("stock_qty", d.name, d.parentfield);
// });

// frappe.ui.form.on("BOM Item", "item_code", function(frm, cdt, cdn) {
// 	var d = locals[cdt][cdn];
// 	frappe.db.get_value('Item', {name: d.item_code}, 'allow_alternative_item', (r) => {
// 		d.allow_alternative_item = r.allow_alternative_item
// 	})
// 	refresh_field("allow_alternative_item", d.name, d.parentfield);
// });

// frappe.ui.form.on("BOM Item", "sourced_by_supplier", function(frm, cdt, cdn) {
// 	var d = locals[cdt][cdn];
// 	if (d.sourced_by_supplier) {
// 		d.rate = 0;
// 		refresh_field("rate", d.name, d.parentfield);
// 	}
// });

// frappe.ui.form.on("BOM Item", "rate", function(frm, cdt, cdn) {
// 	var d = locals[cdt][cdn];
// 	if (d.sourced_by_supplier) {
// 		d.rate = 0;
// 		refresh_field("rate", d.name, d.parentfield);
// 	}
// });

// frappe.ui.form.on("BOM Operation", "operations_remove", function(frm) {
// 	erpnext.bom.calculate_op_cost(frm.doc);
// 	erpnext.bom.calculate_total(frm.doc);
// });

// frappe.ui.form.on("BOM Item", "items_remove", function(frm) {
// 	erpnext.bom.calculate_rm_cost(frm.doc);
// 	erpnext.bom.calculate_total(frm.doc);
// });

// frappe.tour['BOM'] = [
// 	{
// 		fieldname: "item",
// 		title: "Item",
// 		description: __("Select the Item to be manufactured. The Item name, UoM, Company, and Currency will be fetched automatically.")
// 	},
// 	{
// 		fieldname: "quantity",
// 		title: "Quantity",
// 		description: __("Enter the quantity of the Item that will be manufactured from this Bill of Materials.")
// 	},
// 	{
// 		fieldname: "with_operations",
// 		title: "With Operations",
// 		description: __("To add Operations tick the 'With Operations' checkbox.")
// 	},
// 	{
// 		fieldname: "items",
// 		title: "Raw Materials",
// 		description: __("Select the raw materials (Items) required to manufacture the Item")
// 	}
// ];

// frappe.ui.form.on("BOM Scrap Item", {
// 	item_code(frm, cdt, cdn) {
// 		const { item_code } = locals[cdt][cdn];
// 	},
// });

// function trigger_process_loss_qty_prompt(frm, cdt, cdn, item_code) {
// 	frappe.prompt(
// 		{
// 			fieldname: "percent",
// 			fieldtype: "Percent",
// 			label: __("% Finished Item Quantity"),
// 			description:
// 				__("Set quantity of process loss item:") +
// 				` ${item_code} ` +
// 				__("as a percentage of finished item quantity"),
// 		},
// 		(data) => {
// 			const row = locals[cdt][cdn];
// 			row.stock_qty = (frm.doc.quantity * data.percent) / 100;
// 			row.qty = row.stock_qty / (row.conversion_factor || 1);
// 			refresh_field("scrap_items");
// 		},
// 		__("Set Process Loss Item Quantity"),
// 		__("Set Quantity")
// 	);
// }

