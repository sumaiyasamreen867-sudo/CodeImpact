def calculate_discount(price, rate=0.20):
    return price * rate

def final_price(price, rate=0.20):
    return price - calculate_discount(price, rate)