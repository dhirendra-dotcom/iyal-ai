from app.domain.product_search import extract_json_payload, normalize_products


def testextract_json_payload_accepts_fenced_json():
    payload = extract_json_payload('''```json\n{"market_summary":"found", "products": []}\n```''')
    assert payload == {"market_summary": "found", "products": []}


def testnormalize_products_drops_invalid_and_limits():
    payload = {
        "products": [
            {"name": "Adaptive Grip A", "brand": "Brand A", "price_text": "₹499"},
            {"name": ""},
            {"name": "Adaptive Grip B", "seller": "Seller B"},
        ]
    }
    products = normalize_products(payload, 1)
    assert len(products) == 1
    assert products[0]["name"] == "Adaptive Grip A"
    assert products[0]["price_text"] == "₹499"
