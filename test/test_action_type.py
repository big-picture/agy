# test/test_action_type.py


from agy.action_type import ActionType


def dummy_callable(*args, **kwargs):  # pragma: no cover - simple stub
    return args, kwargs


def test_action_type_defaults():
    action_type = ActionType(object_name="shipment", method_name="get_status")

    assert action_type.object_name == "shipment"
    assert action_type.method_name == "get_status"
    assert action_type.args == []
    assert action_type.kwargs == {}
    assert action_type.callable is None
    assert action_type.description is None


def test_action_type_with_details():
    action_type = ActionType(
        object_name="global_function",
        method_name="show",
        args=[str],
        kwargs={"level": str},
        callable=dummy_callable,
        description="Display debug information",
    )

    assert action_type.args == [str]
    assert action_type.kwargs == {"level": str}
    assert action_type.callable is dummy_callable
    assert action_type.description == "Display debug information"
