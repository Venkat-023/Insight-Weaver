from reasoning.relationship_mapper import RelationshipMapper


def test_relationship_mapper_defaults_unknown_relation():
    assert RelationshipMapper().normalize("unknown") == "correlates_with"
    assert RelationshipMapper().normalize("INHIBITS") == "inhibits"
