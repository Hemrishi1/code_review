# test_feature.py
def calculate_discount(price, discount):
    # Intentional bug: dividing by 0 or logic flaw
    final_price = price - (price * discount)
    return final_price
