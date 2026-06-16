from __future__ import annotations


def format_orders(data: dict) -> list:
    orders = data.get("orders", [])
    result = []
    for order in orders:
        pricing = order.get("pricingSummary", {})
        total_info = pricing.get("total", {})
        total_str = f"{total_info.get('value', '')} {total_info.get('currency', '')}".strip()

        line_items = order.get("lineItems", [])
        formatted_line_items = []
        tracking = []
        for li in line_items:
            price_info = li.get("lineItemCost", {})
            formatted_line_items.append({
                "title": li.get("title"),
                "quantity": li.get("quantity"),
                "price": f"{price_info.get('value', '')} {price_info.get('currency', '')}".strip(),
            })
            delivery_info = li.get("deliveryInfo", {})
            if delivery_info:
                tracking.append({
                    "carrier": delivery_info.get("carrierCode"),
                    "number": delivery_info.get("trackingNumber"),
                    "status": li.get("lineItemFulfillmentStatus"),
                })

        result.append({
            "order_id": order.get("orderId"),
            "status": order.get("orderFulfillmentStatus"),
            "created": order.get("creationDate"),
            "total": total_str,
            "item_count": len(line_items),
            "line_items": formatted_line_items,
            "tracking": tracking,
        })
    return result


def format_order_detail(data: dict) -> dict:
    pricing = data.get("pricingSummary", {})
    total_info = pricing.get("total", {})

    fulfillment = data.get("fulfillmentStartInstructions", [{}])
    ship_to = {}
    if fulfillment:
        shipping_step = fulfillment[0].get("shippingStep", {})
        ship_to_raw = shipping_step.get("shipTo", {})
        addr = ship_to_raw.get("contactAddress", {})
        ship_to = {
            "name": ship_to_raw.get("fullName"),
            "address1": addr.get("addressLine1"),
            "address2": addr.get("addressLine2"),
            "city": addr.get("city"),
            "state": addr.get("stateOrProvince"),
            "zip": addr.get("postalCode"),
            "country": addr.get("countryCode"),
        }

    line_items = data.get("lineItems", [])
    formatted_line_items = []
    for li in line_items:
        price_info = li.get("lineItemCost", {})
        delivery_info = li.get("deliveryInfo", {})
        formatted_line_items.append({
            "title": li.get("title"),
            "quantity": li.get("quantity"),
            "price": f"{price_info.get('value', '')} {price_info.get('currency', '')}".strip(),
            "fulfillment_status": li.get("lineItemFulfillmentStatus"),
            "tracking_carrier": delivery_info.get("carrierCode"),
            "tracking_number": delivery_info.get("trackingNumber"),
        })

    return {
        "order_id": data.get("orderId"),
        "status": data.get("orderFulfillmentStatus"),
        "created": data.get("creationDate"),
        "total": f"{total_info.get('value', '')} {total_info.get('currency', '')}".strip(),
        "ship_to": ship_to,
        "line_items": formatted_line_items,
        "payment_summary": {
            "subtotal": pricing.get("priceSubtotal", {}).get("value"),
            "shipping": pricing.get("deliveryCost", {}).get("value"),
            "tax": pricing.get("tax", {}).get("value"),
            "total": total_info.get("value"),
            "currency": total_info.get("currency"),
        },
    }


def format_search_results(raw: dict) -> dict:
    return {
        "total": raw.get("total", 0),
        "results": [format_item_summary(item) for item in raw.get("itemSummaries", [])],
    }


def format_item_summary(item: dict) -> dict:
    price_info = item.get("price", {})
    seller_info = item.get("seller", {})
    image_info = item.get("image", {})

    return {
        "itemId": item.get("itemId"),
        "title": item.get("title"),
        "price": {
            "value": price_info.get("value"),
            "currency": price_info.get("currency"),
        },
        "condition": item.get("condition"),
        "listingType": item.get("buyingOptions", [None])[0],
        "itemWebUrl": item.get("itemWebUrl"),
        "seller": {
            "username": seller_info.get("username"),
            "feedbackScore": seller_info.get("feedbackScore"),
            "feedbackPercentage": seller_info.get("feedbackPercentage"),
        },
        "image": image_info.get("imageUrl"),
        "shortDescription": item.get("shortDescription"),
    }


def format_item_detail(raw: dict) -> dict:
    base = format_item_summary(raw)

    shipping_options = [
        {
            "shippingCost": opt.get("shippingCost", {}).get("value"),
            "currency": opt.get("shippingCost", {}).get("currency"),
            "shippingServiceCode": opt.get("shippingServiceCode"),
            "shippingType": opt.get("type"),
        }
        for opt in raw.get("shippingOptions", [])
    ]

    return_policy = raw.get("returnTerms", {})

    categories = [
        cat.get("categoryName")
        for cat in raw.get("categories", [])
        if cat.get("categoryName")
    ]

    item_specifics = [
        {"name": aspect.get("name"), "value": aspect.get("value")}
        for aspect in raw.get("localizedAspects", [])
    ]

    return {
        **base,
        "description": raw.get("description"),
        "categories": categories,
        "shippingOptions": shipping_options,
        "returnTerms": {
            "returnsAccepted": return_policy.get("returnsAccepted"),
            "returnPeriod": return_policy.get("returnPeriod", {}).get("value"),
            "returnPeriodUnit": return_policy.get("returnPeriod", {}).get("unit"),
            "refundMethod": return_policy.get("refundMethod"),
            "returnMethod": return_policy.get("returnMethod"),
        },
        "itemSpecifics": item_specifics,
        "quantityAvailable": raw.get("estimatedAvailabilities", [{}])[0].get(
            "estimatedAvailableQuantity"
        )
        if raw.get("estimatedAvailabilities")
        else None,
    }
