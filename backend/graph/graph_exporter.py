from graph.graph_builder import KnowledgeGraphBuilder


class GraphExporter:
    def __init__(self, builder: KnowledgeGraphBuilder) -> None:
        self.builder = builder

    def export(self, paper_ids: list[int] | None = None) -> dict:
        return self.builder.export_graph_json(paper_ids)
