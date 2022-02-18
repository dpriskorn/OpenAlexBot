from openalexapi.work import WorkType, Work  # type: ignore
from pydantic import BaseModel


class WorkTypeToQid(BaseModel):
    work: Work

    def get_qid(self):
        if self.work.type == WorkType.BOOK:
            return "Q13442814"
        elif self.work.type == WorkType.JOURNAL_ARTICLE:
            return "Q13442814"
        elif self.work.type == WorkType.BOOK_CHAPTER:
            return "Q21481766"
        else:
            raise ValueError(f"{self.work.type} is not "
                             f"supported, report an issue here "
                             f"https://github.com/dpriskorn/OpenAlexBot/issues.")