from __future__ import annotations


def _parse_orders_xml(xml_text: str) -> list[dict]:
    """Parse GetOrders Trading API XML response into a list of order dicts."""
    import xml.etree.ElementTree as ET
    ns = "urn:ebay:apis:eBLBaseComponents"

    def tag(name: str) -> str:
        return f"{{{ns}}}{name}"

    def text(el, path: str) -> str:
        parts = path.split("/")
        cur = el
        for p in parts:
            if cur is None:
                return ""
            cur = cur.find(tag(p))
        return (cur.text or "").strip() if cur is not None else ""

    root = ET.fromstring(xml_text)

    # Check for API errors
    ack = text(root, "Ack")
    if ack not in ("Success", "Warning"):
        errors = []
        for err in root.findall(f".//{tag('Errors')}"):
            errors.append(text(err, "LongMessage") or text(err, "ShortMessage"))
        raise RuntimeError(f"eBay API error ({ack}): {'; '.join(errors)}")

    orders = []
    for order_el in root.findall(f".//{tag('Order')}"):
        order_id = text(order_el, "OrderID")
        status = text(order_el, "OrderStatus")
        created = text(order_el, "CreatedTime")
        total = text(order_el, "Total")
        currency = order_el.find(f".//{tag('Total')}")
        currency_id = currency.attrib.get("currencyID", "USD") if currency is not None else "USD"

        # Line items
        items = []
        for trans in order_el.findall(f".//{tag('Transaction')}"):
            title = text(trans, "Item/Title")
            item_id = text(trans, "Item/ItemID")
            qty = text(trans, "QuantityPurchased")
            price = text(trans, "TransactionPrice")
            price_currency = ""
            tp = trans.find(f".//{tag('TransactionPrice')}")
            if tp is not None:
                price_currency = tp.attrib.get("currencyID", "USD")
            items.append({
                "title": title,
                "item_id": item_id,
                "quantity": qty,
                "price": f"{price} {price_currency}".strip(),
            })

        # Tracking is in ShippingDetails/ShipmentTrackingDetails
        tracking = []
        for detail in order_el.findall(f".//{tag('ShipmentTrackingDetails')}"):
            carrier = text(detail, "ShippingCarrierUsed")
            number = text(detail, "ShipmentTrackingNumber")
            if carrier or number:
                tracking.append({"carrier": carrier, "tracking_number": number})

        shipping_service = text(order_el, "ShippingDetails/ShippingServiceOptions/ShippingServiceName") or \
                           text(order_el, "ShippingDetails/ShippingServiceSelected/ShippingServiceName")

        orders.append({
            "order_id": order_id,
            "status": status,
            "created": created,
            "total": f"{total} {currency_id}".strip(),
            "items": items,
            "tracking": tracking,
            "shipping_service": shipping_service,
        })

    return orders


def format_orders(xml_text: str) -> list[dict]:
    return _parse_orders_xml(xml_text)


def format_order_detail(xml_text: str) -> list[dict]:
    return _parse_orders_xml(xml_text)


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
