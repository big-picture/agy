# test/test_action_call.py


from agy.action_call import ActionCall


def test_action_call_defaults():
    call = ActionCall(object_name="email", method_name="send")

    assert call.object_name == "email"
    assert call.method_name == "send"
    assert call.args == []
    assert call.kwargs == {}
    assert call.output == "result"


def test_action_call_with_args_kwargs():
    call = ActionCall(
        object_name="global_function",
        method_name="add",
        args=[(1, True), ("value", False)],
        kwargs={"count": (3, True), "context_key": ("total", False)},
        output="sum",
    )

    assert call.args == [(1, True), ("value", False)]
    assert call.kwargs == {"count": (3, True), "context_key": ("total", False)}
    assert call.output == "sum"

    # Helper methods should expose pure values
    assert call.get_args_values() == [1, "value"]
    assert call.get_kwargs_values() == {"count": 3, "context_key": "total"}
