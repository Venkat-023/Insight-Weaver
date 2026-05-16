class PubMedFetcher:
    def fetch(self, pubmed_id: str) -> dict:
        from Bio import Entrez

        handle = Entrez.efetch(db="pubmed", id=pubmed_id, rettype="abstract", retmode="xml")
        return {"pubmed_id": pubmed_id, "xml": handle.read()}
