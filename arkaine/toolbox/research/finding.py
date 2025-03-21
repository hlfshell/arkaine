from typing import Any, Dict, Optional

from arkaine.utils.resource import Resource


class Finding:

    def __init__(
        self,
        resource: Resource,
        summary: str,
        content: str,
        research_id: Optional[str] = None,
    ):
        self.source = f"{resource.name} - {resource.source}"
        self.summary = summary
        self.content = content
        self.resource = resource
        self.research_id = research_id

    def to_json(self):
        return {
            "content": self.content,
            "summary": self.summary,
            "resource": self.resource.to_json(),
            "research_id": self.research_id,
        }

    @classmethod
    def from_json(cls, json: Dict[str, Any]):
        return cls(
            Resource.from_json(json["resource"]),
            json["summary"],
            json["content"],
            json["research_id"],
        )

    def __str__(self):
        resource = f"{self.resource.name} - {self.resource.source}"
        return f"{resource}\n{self.summary}\n{self.content}"

    def __repr__(self):
        return self.__str__()


class CombinedFinding(Finding):
    """
    CombinedFinding is a combination of multiple findings, with a generated summary
    and its own unique embedding. The purpose is to combine multiple findings into
    a more comprehensive but concise expression, while still allowing the original
    findings and thus references to be utilized for reference tracking.
    """

    def __init__(
        self,
        findings: List[Finding],
        summary: Optional[str] = None,
        id: Optional[str] = None,
    ):
        self.__findings = findings
        self.__summary = summary
        self.__id = id

    def to_json(self):
        return {
            "findings": [finding.to_json() for finding in self.__findings],
            "summary": self.__summary,
            "id": self.__id,
        }

    @classmethod
    def from_json(cls, json: Dict[str, Any]):
        return cls(
            [Finding.from_json(finding) for finding in json["findings"]],
            json["summary"],
            json["id"],
        )

    @classmethod
    def combine(
        self, findings: List[Finding], combiner, embedding_model: EmbeddingModel
    ) -> CombinedFinding:
        """
        Combine the findings and return a new CombinedFinding.
        """
        pass
