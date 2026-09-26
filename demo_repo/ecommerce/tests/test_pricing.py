from pricing import calculate_discount, final_price

def test_discount():
    assert calculate_discount(100, 0.10) == 10

def test_final_price():
    assert final_price(100, 0.10) == 90