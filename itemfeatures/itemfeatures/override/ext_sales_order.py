# import SalesOrder
from erpnext.selling.doctype.sales_order.sales_order import SalesOrder
import frappe;
from erpnext.stock.stock_balance import get_reserved_qty, update_bin_qty


class ExtSalesOrder(SalesOrder):
	def update_reserved_qty(self, so_item_rows=None):
		"""update requested qty (before ordered_qty is updated)"""
		item_wh_list = []

		def _valid_for_reserve(item_code, warehouse, custom_feature):
			if (
				item_code
				and warehouse
				and [item_code, warehouse] not in item_wh_list
				and frappe.get_cached_value("Item", item_code, "is_stock_item")
			):
				item_wh_list.append([item_code, warehouse, custom_feature])

		for d in self.get("items"):
			if (not so_item_rows or d.name in so_item_rows) and not d.delivered_by_supplier:
				if self.has_product_bundle(d.item_code):
					for p in self.get("packed_items"):
						if p.parent_detail_docname == d.name and p.parent_item == d.item_code:
							_valid_for_reserve(p.item_code, p.warehouse, p.custom_feature)
				else:
					_valid_for_reserve(d.item_code, d.warehouse, d.custom_feature)

		for item_code, warehouse, feature in item_wh_list:
			update_bin_qty(item_code, warehouse, {"reserved_qty": get_reserved_qty(item_code, warehouse)}, feature=feature)
