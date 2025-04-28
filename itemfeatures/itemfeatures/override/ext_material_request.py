from erpnext.stock.doctype.material_request.material_request import MaterialRequest
import frappe
from erpnext.stock.stock_balance import get_indented_qty, update_bin_qty


class ExtMaterialRequest(MaterialRequest):
	def update_requested_qty(self, mr_item_rows=None):
		"""update requested qty (before ordered_qty is updated)"""
		item_wh_list = []
		for d in self.get("items"):
			if (
				(not mr_item_rows or d.name in mr_item_rows)
				and [d.item_code, d.warehouse] not in item_wh_list
				and d.warehouse
				and frappe.db.get_value("Item", d.item_code, "is_stock_item") == 1
			):
				item_wh_list.append([d.item_code, d.warehouse, d.custom_feature])

		for item_code, warehouse, feature in item_wh_list:
			update_bin_qty(
				item_code,
				warehouse,
				{
					"indented_qty": get_indented_qty(item_code, warehouse),
				},
				feature=feature
			)