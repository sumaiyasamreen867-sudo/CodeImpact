from checkout import calculate_total

def test_checkout_total():
    assert calculate_total(1, 2) == 180