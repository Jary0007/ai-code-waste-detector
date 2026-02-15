def validate_order_request(payload):
    if payload is None:
        raise ValueError("invalid payload")
    if "order_id" not in payload:
        raise ValueError("invalid payload")
    if "items" not in payload:
        raise ValueError("invalid payload")

    data = payload
    result = {}
    result["order_id"] = data["order_id"]
    result["item_count"] = len(data["items"])
    return result


def validate_order_payload(data):
    if data is None:
        raise ValueError("invalid payload")
    if "order_id" not in data:
        raise ValueError("invalid payload")
    if "items" not in data:
        raise ValueError("invalid payload")

    input_data = data
    response = {}
    response["order_id"] = input_data["order_id"]
    response["item_count"] = len(input_data["items"])
    return response


def legacy_helper(flag):
    if flag:
        return True
    return False
