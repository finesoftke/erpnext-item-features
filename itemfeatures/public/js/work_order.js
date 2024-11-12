

frappe.ui.form.on("Work Order", {


    item_features: function(frm) {
		frm.trigger('bom_no');
	},
    
    required_items_on_form_rendered: function(frm, cdt, cdn) {
        document.querySelectorAll
        $(document).find('button[data-fieldname="edit_item_features"]').addClass('btn-primary');
        frappe.call({
            method: "itemfeatures.itemfeatures.utils.get_item_features_for_child_table",
            args: {
                "parent_doctype": "Work Order",
                "parent_docname": cdn,
                "table_field": "required_items",
                "row_name": frm.selected_doc.name
            },
            freeze: true,
            callback(r) {
                console.log(r);
                if(r.message) {
                    frappe.model.set_value("Work Order Item", frm.selected_doc.name, "features", r.message);
                }
            }
        });
        //frappe.model.set_value("Work Order Item", frm.selected_doc.name, "features", []);
    },
})

frappe.ui.form.on('Work Order Item', {
    edit_item_features: (frm, cdt, cdn) => {
        const fields = [];

        fields.push({
            fieldtype: 'Table MultiSelect',
            label: __('Features'),
            fieldname: 'features',
            options: "Item Feature Multiselect",
            default: frm.selected_doc.features
        })

        let dialog = frappe.prompt(fields, data => {
            let feats = [];

             data.features.forEach((f)=> {
                feats.push(f.item_feature);
            });

            frappe.call({
                method: "itemfeatures.itemfeatures.utils.add_item_features_for_child_table",
                args: {
                    "parent_doctype": "Work Order",
                    "parent_docname": frm.doc.name,
                    "table_field": "required_items",
                    "row_name": frm.selected_doc.name,
                    "features": feats
                },
                freeze: true,
                callback(r) {
                    console.log(r);
                    if(r.message) {
                        frm.refresh();
                    }
                }
            });

        }, __("Edit Item Features For " + frm.selected_doc.item_code), __("Save Item Features"));
    }
})