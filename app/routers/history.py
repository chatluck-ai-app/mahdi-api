from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..auth import current_device
from ..db import Conversation, Device, Message, get_db

router = APIRouter(prefix="/v1/history", tags=["history"])


@router.get("")
def list_conversations(device: Device = Depends(current_device), db: Session = Depends(get_db)):
    rows = (
        db.query(Conversation)
        .filter(Conversation.device_id == device.id)
        .order_by(Conversation.updated_at.desc())
        .limit(100)
        .all()
    )
    result = []
    for conv in rows:
        last = (
            db.query(Message)
            .filter(Message.conversation_id == conv.id)
            .order_by(Message.id.desc())
            .first()
        )
        count = db.query(func.count(Message.id)).filter(Message.conversation_id == conv.id).scalar()
        result.append(
            {
                "id": conv.id,
                "title": conv.title,
                "style": conv.style,
                "updated_at": conv.updated_at,
                "message_count": count,
                "last_message": last.content[:200] if last else "",
            }
        )
    return {"conversations": result}


def _own_conversation(db: Session, device: Device, conversation_id: int) -> Conversation:
    conv = db.get(Conversation, conversation_id)
    if conv is None or conv.device_id != device.id:
        raise HTTPException(status_code=404, detail="conversation not found")
    return conv


@router.get("/{conversation_id}")
def get_conversation(
    conversation_id: int, device: Device = Depends(current_device), db: Session = Depends(get_db)
):
    conv = _own_conversation(db, device, conversation_id)
    rows = (
        db.query(Message)
        .filter(Message.conversation_id == conv.id)
        .order_by(Message.id.asc())
        .all()
    )
    return {
        "id": conv.id,
        "title": conv.title,
        "style": conv.style,
        "messages": [
            {"role": m.role, "content": m.content, "provider": m.provider, "created_at": m.created_at}
            for m in rows
        ],
    }


@router.delete("/{conversation_id}")
def delete_conversation(
    conversation_id: int, device: Device = Depends(current_device), db: Session = Depends(get_db)
):
    conv = _own_conversation(db, device, conversation_id)
    db.query(Message).filter(Message.conversation_id == conv.id).delete()
    db.delete(conv)
    db.commit()
    return {"deleted": conversation_id}
