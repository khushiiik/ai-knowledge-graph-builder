from uuid import UUID
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.services.document_service import load_csv
from app.core.exceptions import DocumentNotFoundException
from app.dependencies import get_db, get_current_active_user
from app.models.document import Document as DocumentModel
from app.models.user import User as UserModel
from app.tools.chart_generator import ChartGenerator

router = APIRouter(prefix="/chart", tags=["chart"])


class ChartRequest(BaseModel):
    document_id: UUID
    chart_type: str
    x: str
    y: str


@router.post("/chart")
def create_chart(
    payload: ChartRequest,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
):
    # Enforce strict multi-tenant user data isolation: filter by both document ID and user ID
    document = (
        db.query(DocumentModel)
        .filter(
            DocumentModel.id == payload.document_id,
            DocumentModel.user_id == current_user.id,
        )
        .first()
    )
    if not document:
        raise DocumentNotFoundException()

    loaded_dataframe = load_csv(document)

    filename = ChartGenerator().generate(
        dataframe=loaded_dataframe,
        chart_type=payload.chart_type,
        x=payload.x,
        y=payload.y,
    )

    return {"url": f"/generated/charts/{filename}"}
