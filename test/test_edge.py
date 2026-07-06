# test/test_edge.py

from agy.edge import Edge
from agy.node import Node


def test_edge_creation_with_node():
    """Test dass Edge mit einem Node erstellt werden kann"""
    node = Node(name="target_node", control_type="deterministic")
    edge = Edge(target=node, condition="success")

    assert edge.target == node
    assert edge.target.name == "target_node"
    assert edge.condition == "success"


def test_edge_creation_without_condition():
    """Test dass Edge auch ohne condition erstellt werden kann (wird None sein, aber sollte in Praxis 'true' sein)"""
    node = Node(name="target_node", control_type="stochastic")
    edge = Edge(
        target=node
    )  # condition defaults to None in Edge, but will be "true" when parsed from YAML

    assert edge.target == node
    assert (
        edge.condition is None
    )  # Edge allows None, but YAML parser converts to "true"


def test_edge_target_access():
    """Test dass man auf das target Node zugreifen kann"""
    node = Node(name="my_node", control_type="deterministic")
    edge = Edge(target=node, condition="else")

    assert edge.target.name == "my_node"
    assert edge.target.control_type == "deterministic"


def test_edge_with_expression_conditions():
    """Test dass Edge mit verschiedenen Expressions funktioniert"""
    node = Node(name="target_node", control_type="deterministic")

    # Verschiedene Expressions
    edge1 = Edge(target=node, condition="x")
    assert edge1.condition == "x"

    edge2 = Edge(target=node, condition="x > y")
    assert edge2.condition == "x > y"

    edge3 = Edge(target=node, condition="x == z and a")
    assert edge3.condition == "x == z and a"

    edge4 = Edge(target=node, condition="status == 'success'")
    assert edge4.condition == "status == 'success'"

    # TODO: Add direct condition evaluation coverage later.


def test_edge_evaluate_simple():
    """Test dass Edge einfache Conditions evaluieren kann"""
    from agy.node import Node

    node = Node(name="target_node", control_type="deterministic")
    edge = Edge(target=node, condition="success")

    # Success True
    context1 = {"success": True}
    assert edge.evaluate(context1) is True

    # Success False
    context2 = {"success": False}
    assert edge.evaluate(context2) is False


def test_edge_evaluate_expressions():
    """Test dass Edge Expressions evaluieren kann"""
    from agy.node import Node

    node = Node(name="target_node", control_type="deterministic")

    # Einfache Vergleiche
    edge1 = Edge(target=node, condition="x > y")
    context1 = {"x": 5, "y": 3}
    assert edge1.evaluate(context1) is True

    edge2 = Edge(target=node, condition="x < y")
    assert edge2.evaluate(context1) is False

    edge3 = Edge(target=node, condition="x == 5")
    assert edge3.evaluate(context1) is True

    # Komplexere Expressions
    edge4 = Edge(target=node, condition="x > y and z < 10")
    context2 = {"x": 10, "y": 5, "z": 2}
    assert edge4.evaluate(context2) is True

    edge5 = Edge(target=node, condition="x > 20 or y < 10")
    assert edge5.evaluate(context2) is True


def test_edge_evaluate_undefined():
    """Test dass Edge mit undefined Variablen umgehen kann"""
    from agy.node import Node

    node = Node(name="target_node", control_type="deterministic")
    edge = Edge(target=node, condition="undefined_var > 5")

    # Variable nicht im Context
    assert edge.evaluate({}) is False


def test_edge_evaluate_true():
    """Test dass Edge "True" Condition korrekt behandelt"""
    from agy.node import Node

    node = Node(name="target_node", control_type="deterministic")
    edge = Edge(target=node, condition="True")

    # "True" condition should always evaluate to True
    assert edge.evaluate({}) is True
    assert edge.evaluate({"x": 5}) is True


def test_edge_evaluate_none_condition():
    """Test dass Edge mit None condition False zurückgibt"""
    from agy.node import Node

    node = Node(name="target_node", control_type="deterministic")
    edge = Edge(target=node, condition=None)

    # None condition should return False (should not happen in practice)
    assert edge.evaluate({}) is False
