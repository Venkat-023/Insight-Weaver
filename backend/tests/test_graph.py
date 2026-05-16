from graph.graph_queries import TOPIC_PAPERS


def test_topic_query_contains_topic_parameter():
    assert "$topic" in TOPIC_PAPERS
