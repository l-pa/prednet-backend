import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlmodel import func, select

from app.api.deps import CurrentUser, SessionDep
from app.models import (
    FavoriteComponent,
    FavoriteComponentCreate,
    FavoriteComponentPublic,
    FavoriteComponentUpdate,
    FavoriteComponentsPublic,
    Message,
)
from pydantic import BaseModel


router = APIRouter(prefix="/favorites", tags=["favorites"])


@router.get("/", response_model=FavoriteComponentsPublic)
def read_favorites(
    session: SessionDep, current_user: CurrentUser, skip: int = 0, limit: int = 100
) -> Any:
    if current_user.is_superuser:
        count_stmt = select(func.count()).select_from(FavoriteComponent)
        count = session.exec(count_stmt).one()
        stmt = select(FavoriteComponent).offset(skip).limit(limit)
        items = session.exec(stmt).all()
    else:
        count_stmt = (
            select(func.count())
            .select_from(FavoriteComponent)
            .where(FavoriteComponent.owner_id == current_user.id)
        )
        count = session.exec(count_stmt).one()
        stmt = (
            select(FavoriteComponent)
            .where(FavoriteComponent.owner_id == current_user.id)
            .offset(skip)
            .limit(limit)
        )
        items = session.exec(stmt).all()

    return FavoriteComponentsPublic(data=items, count=count)


@router.get("/{id}", response_model=FavoriteComponentPublic)
def read_favorite(
    session: SessionDep, current_user: CurrentUser, id: uuid.UUID
) -> Any:
    item = session.get(FavoriteComponent, id)
    if not item:
        raise HTTPException(status_code=404, detail="Favorite not found")
    if not current_user.is_superuser and (item.owner_id != current_user.id):
        raise HTTPException(status_code=400, detail="Not enough permissions")
    return item


@router.post("/", response_model=FavoriteComponentPublic)
def create_favorite(
    *, session: SessionDep, current_user: CurrentUser, item_in: FavoriteComponentCreate
) -> Any:
    # prevent duplicates per user for same (network, filename, component_id)
    existing = session.exec(
        select(FavoriteComponent)
        .where(FavoriteComponent.owner_id == current_user.id)
        .where(FavoriteComponent.network_name == item_in.network_name)
        .where(FavoriteComponent.filename == item_in.filename)
        .where(FavoriteComponent.component_id == item_in.component_id)
    ).first()
    if existing:
        return existing

    item = FavoriteComponent.model_validate(item_in, update={"owner_id": current_user.id})
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@router.put("/{id}", response_model=FavoriteComponentPublic)
def update_favorite(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    id: uuid.UUID,
    item_in: FavoriteComponentUpdate,
) -> Any:
    item = session.get(FavoriteComponent, id)
    if not item:
        raise HTTPException(status_code=404, detail="Favorite not found")
    if not current_user.is_superuser and (item.owner_id != current_user.id):
        raise HTTPException(status_code=400, detail="Not enough permissions")
    update_dict = item_in.model_dump(exclude_unset=True)
    item.sqlmodel_update(update_dict)
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@router.delete("/{id}")
def delete_favorite(
    session: SessionDep, current_user: CurrentUser, id: uuid.UUID
) -> Message:
    item = session.get(FavoriteComponent, id)
    if not item:
        raise HTTPException(status_code=404, detail="Favorite not found")
    if not current_user.is_superuser and (item.owner_id != current_user.id):
        raise HTTPException(status_code=400, detail="Not enough permissions")
    session.delete(item)
    session.commit()
    return Message(message="Favorite deleted successfully")


class FavoriteExists(BaseModel):
    exists: bool
    id: uuid.UUID | None = None


@router.get("/exists", response_model=FavoriteExists)
def favorite_exists(
    session: SessionDep,
    current_user: CurrentUser,
    network_name: str,
    filename: str,
    component_id: int,
) -> Any:
    item = session.exec(
        select(FavoriteComponent)
        .where(FavoriteComponent.owner_id == current_user.id)
        .where(FavoriteComponent.network_name == network_name)
        .where(FavoriteComponent.filename == filename)
        .where(FavoriteComponent.component_id == component_id)
    ).first()
    if item:
        return FavoriteExists(exists=True, id=item.id)
    return FavoriteExists(exists=False, id=None)
