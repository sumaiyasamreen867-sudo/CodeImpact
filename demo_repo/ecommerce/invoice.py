from checkout import calculate_total

def generate_invoice(product_id, quantity):
    total = calculate_total(product_id, quantity)
    return {"product_id": product_id, "quantity": quantity, "total": total}