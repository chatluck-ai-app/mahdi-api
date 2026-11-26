from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import current_device
from ..db import Device
from ..providers import router as provider_router

router = APIRouter(prefix="/v1", tags=["translate"])

TARGET_PROMPTS = {
    "egyptian": "ترجم النص التالي إلى العامية المصرية الطبيعية.",
    "fusha": "ترجم النص التالي إلى اللغة العربية الفصحى.",
    "en": "Translate the following text into natural English.",
}


class TranslateIn(BaseModel):
    text: str
    target: Literal["egyptian", "fusha", "en"] = "fusha"


class TranslateOut(BaseModel):
    translation: str
    target: str
    provider: str


@router.post("/translate", response_model=TranslateOut)
async def translate(body: TranslateIn, device: Device = Depends(current_device)):
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="empty text")
    system = TARGET_PROMPTS[body.target] + " أعد الترجمة فقط دون أي شرح أو ملاحظات."
    try:
        translation, provider = await provider_router.complete(
            [{"role": "user", "content": text}], system
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return TranslateOut(translation=translation.strip(), target=body.target, provider=provider)
