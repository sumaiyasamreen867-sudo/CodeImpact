from pricing import final_price
from product import get_product_price

def calculate_total(product_id, quantity):
    price = get_product_price(product_id)
    return final_price(price * quantity)