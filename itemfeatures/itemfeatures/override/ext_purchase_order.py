# import PurchaseOrder from erpnext
from erpnext.accounts.doctype.purchase_order.purchase_order import PurchaseOrder
from erpnext.stock.stock_balance import get_ordered_qty, update_bin_qty
from erpnext.stock.utils import get_bin
import frappe


class CustomPurchaseOrder(PurchaseOrder):
	def update_ordered_qty(self, po_item_rows=None):
		"""update requested qty (before ordered_qty is updated)"""
		item_wh_list = []
		for d in self.get("items"):
			if (
				(not po_item_rows or d.name in po_item_rows)
				and [d.item_code, d.warehouse] not in item_wh_list
				and frappe.get_cached_value("Item", d.item_code, "is_stock_item")
				and d.warehouse
				and not d.delivered_by_supplier
			):
				item_wh_list.append([d.item_code, d.warehouse, d.custom_feature])
		for item_code, warehouse, feature in item_wh_list:
			update_bin_qty(item_code, warehouse, {"ordered_qty": get_ordered_qty(item_code, warehouse)}, feature=feature)



	def update_reserved_qty_for_subcontract(self):
		if self.is_old_subcontracting_flow:
			for d in self.supplied_items:
				if d.rm_item_code:
					stock_bin = get_bin(d.rm_item_code, d.reserve_warehouse, d.custom_feature)
					stock_bin.update_reserved_qty_for_sub_contracting(subcontract_doctype="Purchase Order")

