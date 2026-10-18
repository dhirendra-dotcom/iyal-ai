def count_user_turn(callback_context):
    """Count user messages so tools can tell the first turn of a conversation apart."""
    callback_context.state["user_turn_count"] = int(callback_context.state.get("user_turn_count") or 0) + 1
    return None
