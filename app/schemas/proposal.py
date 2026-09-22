from pydantic import BaseModel, field_validator


class ProposalCreate(BaseModel):
    question: str
    category: str = "Otro"
    description: str | None = None
    proposer_contact: str | None = None

    @field_validator("question")
    @classmethod
    def question_valid(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("La pregunta no puede estar vacía")
        # Mismo límite que el sembrador (veredikt.md §5: 70, meta 65)
        if len(v) > 70:
            raise ValueError("Máximo 70 caracteres")
        return v

    @field_validator("category")
    @classmethod
    def category_valid(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            return "Otro"
        return v[:50]

    @field_validator("description")
    @classmethod
    def description_valid(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        if len(v) > 2000:
            raise ValueError("Máximo 2,000 caracteres")
        return v

    @field_validator("proposer_contact")
    @classmethod
    def contact_valid(cls, v: str | None) -> str | None:
        # Free-form: accepts an email OR a username, no format check.
        if v is None:
            return None
        v = v.strip()
        return v[:200] if v else None
