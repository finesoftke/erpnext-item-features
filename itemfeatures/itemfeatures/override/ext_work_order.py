import frappe
from frappe.utils import flt, cint
from erpnext.manufacturing.doctype.work_order.work_order import WorkOrder
from erpnext.manufacturing.doctype.bom.bom import (
    get_bom_item_rate,
    validate_bom_no,
)

class ExtWorkOrder(WorkOrder):

    def set_required_items(self, reset_only_qty=False):
        """set required_items for production to keep track of reserved qty"""
        if not reset_only_qty:
            self.required_items = []

        order_features = []
        for feat in self.item_features:
            order_features.append(feat.item_feature)

        operation = None
        if self.get("operations") and len(self.operations) == 1:
            operation = self.operations[0].operation

        if self.bom_no and self.qty:
            item_dict = get_bom_items_as_dict(
                self.bom_no, self.company, qty=self.qty, fetch_exploded=self.use_multi_level_bom
            )

            if reset_only_qty:
                for d in self.get("required_items"):
                    if item_dict.get(d.item_code):
                        d.required_qty = item_dict.get(d.item_code).get("qty")
                        d.bom_qty = item_dict.get(d.item_code).get("qty")

                    if not d.operation:
                        d.operation = operation
            else:
                for item in sorted(item_dict.values(), key=lambda d: d["idx"] or float("inf")):
                    if not item.included_in_feature or item.included_in_feature in order_features:
                        self.append(
                            "required_items",
                            {
                                "rate": item.rate,
                                "amount": item.rate * item.qty,
                                "operation": item.operation or operation,
                                "item_code": item.item_code,
                                "item_name": item.item_name,
                                "description": item.description,
                                "allow_alternative_item": item.allow_alternative_item,
                                "required_qty": item.qty,
                                "bom_qty": item.qty,
                                "source_warehouse": item.source_warehouse or item.default_warehouse,
                                "include_item_in_manufacturing": item.include_item_in_manufacturing,
                            },
                        )

                    if not self.project:
                        self.project = item.get("project")

            self.set_available_qty()

        # if self.item_features and self.qty:
        #     for feat in self.item_features:
        #         feat_doc = frappe.get_doc("Item Feature", feat.item_feature)

        #         if len(feat_doc.items) > 0:
        #             for it in feat_doc.items:
        #                 total_qty = (it.qty * self.qty)
        #                 added = False
        #                 for d in self.get("required_items"):
        #                     if it.item_code == d.item_code:
        #                         added = True
        #                         if reset_only_qty:
        #                             d.required_qty = total_qty + d.bom_qty
        #                             d.features_qty = total_qty

        #                         if not reset_only_qty:
        #                             d.required_qty = d.required_qty + total_qty
        #                             d.amount = d.amount + (d.rate * total_qty)
        #                             d.features_qty = total_qty
                        
        #                 if not added and not reset_only_qty:
        #                     self.append(
        #                         "required_items",
        #                         {
        #                             "rate": it.rate,
        #                             "amount": it.rate * total_qty,
        #                             "operation": it.operation or operation,
        #                             "item_code": it.item_code,
        #                             "item_name": it.item_name,
        #                             "description": it.description,
        #                             "allow_alternative_item": it.allow_alternative_item,
        #                             "required_qty": total_qty,
        #                             "bom_qty": 0,
        #                             "features_qty": total_qty,
        #                             "source_warehouse": it.source_warehouse,
        #                             "include_item_in_manufacturing": it.include_item_in_manufacturing,
        #                         },
        #                     )

        #     self.set_available_qty()

    def set_work_order_operations(self):
        """Fetch operations from BOM and set in 'Work Order'"""

        # def _get_features_operations(qty=1):

        #     features = []

        #     for feat in self.item_features:
        #         features.append(feat.item_feature)
        #     data = frappe.get_all(
        #         "BOM Operation",
        #         filters=[["parent", "in", features]],
        #         fields=[
        #             "operation",
        #             "description",
        #             "workstation",
        #             "idx",
        #             "workstation_type",
        #             "base_hour_rate as hour_rate",
        #             "time_in_mins",
        #             "'' as bom",
        #             "batch_size",
        #             "sequence_id",
        #             "fixed_time",
        #         ],
        #         order_by="idx",
        #     )

        #     for d in data:
        #         if not d.fixed_time:
        #             d.time_in_mins = flt(d.time_in_mins) * flt(qty)
        #         d.status = "Pending"

        #     return data

        def _get_operations(bom_no, qty=1):

            order_features = []
            for feat in self.item_features:
                order_features.append(feat.item_feature)

            ops = frappe.get_all(
                "BOM Operation",
                filters={"parent": bom_no},
                fields=[
                    "operation",
                    "description",
                    "workstation",
                    "idx",
                    "workstation_type",
                    "base_hour_rate as hour_rate",
                    "time_in_mins",
                    "parent as bom",
                    "batch_size",
                    "included_in_feature",
                    "sequence_id",
                    "fixed_time",
                ],
                order_by="idx",
            )
            data = []
            for d in ops:
                if not d.included_in_feature or d.included_in_feature in order_features:
                    if not d.fixed_time:
                        d.time_in_mins = flt(d.time_in_mins) * flt(qty)
                    d.status = "Pending"
                    data.append(d)
            
            return data

        self.set("operations", [])
        if not self.bom_no or not frappe.get_cached_value("BOM", self.bom_no, "with_operations"):
            return

        operations = []

        if self.use_multi_level_bom:
            bom_tree = frappe.get_doc("BOM", self.bom_no).get_tree_representation()
            bom_traversal = reversed(bom_tree.level_order_traversal())

            for node in bom_traversal:
                if node.is_bom:
                    operations.extend(_get_operations(node.name, qty=node.exploded_qty / node.bom_qty))

        bom_qty = frappe.get_cached_value("BOM", self.bom_no, "quantity")
        operations.extend(_get_operations(self.bom_no, qty=1.0 / bom_qty))

        # if len(self.item_features) > 0:
        #     operations.extend(_get_features_operations(qty=1.0 / bom_qty))

        for correct_index, operation in enumerate(operations, start=1):
            operation.idx = correct_index

        self.set("operations", operations)
        self.calculate_time()

    def on_update(self):
        for feat in self.item_features:
            feature = frappe.get_doc("Item Feature", feat.item_feature)
            feature_type = frappe.get_doc("Item Feature Type", feature.type)

            
            for it in self.required_items:
                item = frappe.get_doc("Item", it.item_code)
                docs = frappe.get_all("Item Feature Child Table Values", filters={"parent_name": self.name, "row_name": it.name}, fields=["name"])
                doc = None
                if len(docs) > 0:
                    doc = frappe.get_doc("Item Feature Child Table Values", docs[0].name)
                    doc.features = []
                
                for f in item.item_features:
                    if f.feature_type == feature_type.name:
                        
                        if not doc:
                            doc = frappe.new_doc("Item Feature Child Table Values")
                            doc.parent_doctype = "Work Order"
                            doc.parent_name = self.name
                            doc.table_field = "required_items"
                            doc.row_name = it.name
                        
                        doc.append("features", {
                            "item_feature": feat.item_feature
                        })

                        doc.save()


def get_bom_items_as_dict(
	bom,
	company,
	qty=1,
	fetch_exploded=1,
	fetch_scrap_items=0,
	include_non_stock_items=False,
	fetch_qty_in_stock_uom=True,
):
	item_dict = {}

	# Did not use qty_consumed_per_unit in the query, as it leads to rounding loss
	query = """select
				bom_item.item_code,
				bom_item.idx,
                bom_item.included_in_feature,
				item.item_name,
				sum(bom_item.{qty_field}/ifnull(bom.quantity, 1)) * %(qty)s as qty,
				item.image,
				bom.project,
				bom_item.rate,
				sum(bom_item.{qty_field}/ifnull(bom.quantity, 1)) * bom_item.rate * %(qty)s as amount,
				item.stock_uom,
				item.item_group,
				item.allow_alternative_item,
				item_default.default_warehouse,
				item_default.expense_account as expense_account,
				item_default.buying_cost_center as cost_center
				{select_columns}
			from
				`tab{table}` bom_item
				JOIN `tabBOM` bom ON bom_item.parent = bom.name
				JOIN `tabItem` item ON item.name = bom_item.item_code
				LEFT JOIN `tabItem Default` item_default
					ON item_default.parent = item.name and item_default.company = %(company)s
			where
				bom_item.docstatus < 2
				and bom.name = %(bom)s
				and item.is_stock_item in (1, {is_stock_item})
				{where_conditions}
				group by item_code, stock_uom
				order by idx"""

	is_stock_item = 0 if include_non_stock_items else 1
	if cint(fetch_exploded):
		query = query.format(
			table="BOM Explosion Item",
			where_conditions="",
			is_stock_item=is_stock_item,
			qty_field="stock_qty",
			select_columns=""", bom_item.source_warehouse, bom_item.operation,
				bom_item.include_item_in_manufacturing, bom_item.description, bom_item.rate, bom_item.sourced_by_supplier,
				(Select idx from `tabBOM Item` where item_code = bom_item.item_code and parent = %(parent)s limit 1) as idx""",
		)

		items = frappe.db.sql(
			query, {"parent": bom, "qty": qty, "bom": bom, "company": company}, as_dict=True
		)
	elif fetch_scrap_items:
		query = query.format(
			table="BOM Scrap Item",
			where_conditions="",
			select_columns=", item.description",
			is_stock_item=is_stock_item,
			qty_field="stock_qty",
		)

		items = frappe.db.sql(query, {"qty": qty, "bom": bom, "company": company}, as_dict=True)
	else:
		query = query.format(
			table="BOM Item",
			where_conditions="",
			is_stock_item=is_stock_item,
			qty_field="stock_qty" if fetch_qty_in_stock_uom else "qty",
			select_columns=""", bom_item.uom, bom_item.conversion_factor, bom_item.source_warehouse,
				bom_item.operation, bom_item.include_item_in_manufacturing, bom_item.sourced_by_supplier,
				bom_item.description, bom_item.base_rate as rate """,
		)
		items = frappe.db.sql(query, {"qty": qty, "bom": bom, "company": company}, as_dict=True)

	for item in items:
		if item.item_code in item_dict:
			item_dict[item.item_code]["qty"] += flt(item.qty)
		else:
			item_dict[item.item_code] = item

	for item, item_details in item_dict.items():
		for d in [
			["Account", "expense_account", "stock_adjustment_account"],
			["Cost Center", "cost_center", "cost_center"],
			["Warehouse", "default_warehouse", ""],
		]:
			company_in_record = frappe.db.get_value(d[0], item_details.get(d[1]), "company")
			if not item_details.get(d[1]) or (company_in_record and company != company_in_record):
				item_dict[item][d[1]] = frappe.get_cached_value("Company", company, d[2]) if d[2] else None

	return item_dict

