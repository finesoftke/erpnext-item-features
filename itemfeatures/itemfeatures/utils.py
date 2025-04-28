import frappe
import random
import string
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


@frappe.whitelist()
def get_composite_feature(features):
    """
    Retrieves a composite feature that contains all the features passed as parameters in its child table.
    If no matching composite feature exists, it creates one by calling create_composite_feature.
    
    :param features: List of feature names (or comma separated string) to check for in the composite feature.
    :return: Composite feature name.
    """
    # Ensure features is a list (if passed as a comma separated string)
    if isinstance(features, str):
        features = [f.strip() for f in features.split(",") if f.strip()]
    
    # Fetch all composite features
    composite_features = frappe.db.get_all("Item Feature", filters={"type": "Composite"}, fields=["name"])
    
    for comp in composite_features:
        comp_doc = frappe.get_doc("Item Feature", comp.name)
        # Collect feature values from the child table "child_features"
        child_features = [child.feature for child in comp_doc.get("features")]
        # Check if all the passed features are in the composite feature's child table
        if all(feature in child_features for feature in features):
            return comp_doc.name
    
    # If no matching composite feature exists, create a new one.
    return create_composite_feature(features)

def create_composite_feature(features):
    """
    Creates a new composite feature with a unique 5-letter name.
    
    :param features: List of feature names to add in the composite feature's child table.
    :return: Newly created composite feature as a dictionary.
    """
    unique_name = generate_unique_name(5)
    
    # Create a new composite feature document.
    comp_doc = frappe.get_doc({
        "doctype": "Item Feature",
        "identifier": unique_name,
        "type": "Composite",
        "features": []  # Assuming "child_features" is the child table fieldname
    })
    
    # Append each provided feature to the child table.
    for feature in features:
        comp_doc.append("features", {"feature": feature})
    
    comp_doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return comp_doc.name

def generate_unique_name(length):
    """
    Generates a unique random name consisting of uppercase letters.
    
    :param length: Length of the unique name.
    :return: Unique name string.
    """
    while True:
        name = ''.join(random.choices(string.ascii_uppercase, k=length))
        if not frappe.db.exists("Item Feature", name):
            return name
    
@frappe.whitelist()
def get_features_from_composite(composite_feature_name):
    """
    Retrieves all features inside a composite feature and returns them as a comma-separated string.
    
    :param composite_feature_name: Name of the composite feature.
    :return: Comma-separated string of feature names.
    """

    if not composite_feature_name:
        return
    
    # Fetch the composite feature document
    composite_feature = frappe.get_doc("Item Feature", composite_feature_name)
    
    # Extract features from the child table (assuming "child_features" is the fieldname)
    features = [child.feature for child in composite_feature.get("features", [])]
    
    # Return as a comma-separated string
    return ", ".join(features) if features else ""

@frappe.whitelist()
def fetch_features():
    return frappe.get_all("Item Feature", filters=[["type", "!=", "Composite"]], fields=["name", "identifier"])
