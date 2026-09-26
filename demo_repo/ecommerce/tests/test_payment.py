from payment import process_payment

def test_payment():
    result = process_payment(100)
    assert result["status"] == "success"
    assert result["amount"] == 100