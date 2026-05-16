class RelationshipMapper:
    allowed = {"treats", "inhibits", "activates", "correlates_with", "causes", "similar_to", "contradicts", "part_of"}

    def normalize(self, relationship: str) -> str:
        value = relationship.strip().lower()
        return value if value in self.allowed else "correlates_with"
