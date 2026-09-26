from invoice import generate_invoice
from payment import process_payment

def checkout_order(product_id, quantity):
    invoice = generate_invoice(product_id, quantity)
    payment = process_payment(invoice["total"])
    return {"invoice": invoice, "payment": payment}