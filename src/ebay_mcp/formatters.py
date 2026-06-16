from __future__ import annotations


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
