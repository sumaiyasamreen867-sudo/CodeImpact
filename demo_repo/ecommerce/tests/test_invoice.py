from invoice import generate_invoice

def test_invoice_total():
    assert generate_invoice(1, 2)["total"] == 180