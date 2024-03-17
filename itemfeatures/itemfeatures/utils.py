import frappe
import json

@frappe.whitelist()
def get_item_features_for_child_table(parent_doctype, parent_docname, table_field, row_name):
    docs = frappe.get_all("Item Feature Child Table Values", filters = {
                "parent_doctype": parent_doctype,
                "parent_name": parent_docname,
                "table_field": table_field,
                "row_name": row_name
            }, fields = ["name"])

    if len(docs) > 0: 
        doc = frappe.get_doc("Item Feature Child Table Values", docs[0].name)
        return doc.features

@frappe.whitelist()
def add_item_features_for_child_table(parent_doctype, parent_docname, table_field, row_name, features):

    docs = frappe.get_all("Item Feature Child Table Values", filters={"parent_name": parent_docname, "row_name": row_name}, fields=["name"])
    doc = None
    if len(docs) > 0:
        doc = frappe.get_doc("Item Feature Child Table Values", docs[0].name)
        doc.features = []

    if not doc:
        doc = frappe.new_doc("Item Feature Child Table Values")
        doc.parent_doctype = parent_doctype
        doc.parent_name = parent_docname
        doc.table_field = table_field
        doc.row_name = row_name	
        
    if isinstance(features, str):
        import json

        features = json.loads(features)

    for feat in features:
        doc.append("features", {
            "item_feature": feat
        })
    
    doc.save()
    return doc.features
    