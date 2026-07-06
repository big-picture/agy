# test/test_node.py

from agy.action_call import ActionCall
from agy.edge import Edge
from agy.node import Node


def test_node_creation_deterministic():
    """Test dass Node mit deterministic control_type erstellt werden kann"""
    node = Node(name="node1", control_type="deterministic")

    assert node.name == "node1"
    assert node.control_type == "deterministic"
    assert node.instruction is None


def test_node_creation_stochastic():
    """Test dass Node mit stochastic control_type erstellt werden kann"""
    node = Node(
        name="node2",
        control_type="stochastic",
        instruction="Do something random",
        agent="consc",
        requests=["Do one thing", "Do another thing"],
        options={"mode": "careful"},
        output="agent_output",
        message="agent_message",
    )

    assert node.name == "node2"
    assert node.control_type == "stochastic"
    assert node.instruction == "Do something random"
    assert node.agent == "consc"
    assert node.requests == ["Do one thing", "Do another thing"]
    assert node.options == {"mode": "careful"}
    assert node.output == "agent_output"
    assert node.message == "agent_message"


# test_node_with_context() removed - context attribute no longer exists on Node


def test_node_with_outputs():
    """Test dass Node mit outputs erstellt werden kann"""
    outputs = {"carrier": "str", "tracking_id": "str"}
    node = Node(name="node4", control_type="deterministic", outputs=outputs)

    assert node.outputs == outputs


def test_node_with_actions():
    """Test dass Node mit Actions erstellt werden kann"""
    actions = [
        ActionCall(
            object_name="shipment",
            method_name="get_status",
            args=[("shipment_id", False)],
        ),
        ActionCall(
            object_name="email",
            method_name="send",
            kwargs={"subject": ("Welcome", True)},
        ),
    ]
    node = Node(name="node5", control_type="deterministic", actions=actions)

    assert len(node.actions) == 2
    assert node.actions[0].object_name == "shipment"
    assert node.actions[0].args == [("shipment_id", False)]
    assert node.actions[1].object_name == "email"
    assert node.actions[1].kwargs == {"subject": ("Welcome", True)}


def test_node_with_edges():
    """Test dass Node mit Edges erstellt werden kann"""
    target_node = Node(name="target", control_type="deterministic")
    edges = [
        Edge(target=target_node, condition="success"),
        Edge(target=target_node, condition="x > 5"),
    ]
    node = Node(name="node6", control_type="stochastic", edges=edges)

    assert len(node.edges) == 2
    assert node.edges[0].condition == "success"
    assert node.edges[1].condition == "x > 5"


def test_node_default_values():
    """Test dass Node Default-Werte korrekt setzt"""
    node = Node(name="node7", control_type="deterministic")

    assert node.outputs == {}
    assert node.actions == []
    assert node.edges == []
    assert node.instruction is None
    assert node.agent is None
    assert node.requests == []
    assert node.options == {}
    assert node.output is None
    assert node.message is None
