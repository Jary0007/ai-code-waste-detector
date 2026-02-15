function validateOrderPayload(payload) {
  if (payload == null) {
    throw new Error("invalid payload");
  }
  if (!payload.orderId) {
    throw new Error("invalid payload");
  }
  if (!payload.items) {
    throw new Error("invalid payload");
  }

  const data = payload;
  const result = {};
  result.orderId = data.orderId;
  result.itemCount = data.items.length;
  return result;
}

const validateOrderRequest = (data) => {
  if (data == null) {
    throw new Error("invalid payload");
  }
  if (!data.orderId) {
    throw new Error("invalid payload");
  }
  if (!data.items) {
    throw new Error("invalid payload");
  }

  const input = data;
  const response = {};
  response.orderId = input.orderId;
  response.itemCount = input.items.length;
  return response;
};

function helper(flag) {
  if (flag) {
    return true;
  }
  return false;
}
