"""Firestore 클라이언트 — 앱 전체에서 하나만 만들어 재사용한다.

자격 증명 우선순위
1. FIREBASE_SERVICE_ACCOUNT_JSON  키 JSON 문자열(Render 환경 변수)
2. FIREBASE_SERVICE_ACCOUNT_PATH  키 파일 경로(로컬, 저장소 밖에 둔다)
3. FIRESTORE_EMULATOR_HOST        로컬 에뮬레이터(자격 증명 불필요, FIREBASE_PROJECT_ID 는 demo- 로 시작)
"""
import json
import os
import threading

import firebase_admin
from firebase_admin import credentials, firestore
from google.auth.credentials import AnonymousCredentials

from .config import get_settings
from .errors import AppError

_lock = threading.Lock()
_db = None


def _credential(s):
    if s.firebase_service_account_json:
        try:
            return credentials.Certificate(json.loads(s.firebase_service_account_json))
        except (ValueError, KeyError) as e:
            raise AppError(503, "NOT_CONFIGURED", "FIREBASE_SERVICE_ACCOUNT_JSON 형식이 올바르지 않습니다.") from e
    if s.firebase_service_account_path:
        return credentials.Certificate(s.firebase_service_account_path)
    return None


def get_db():
    global _db
    if _db is not None:
        return _db
    with _lock:
        if _db is not None:
            return _db
        s = get_settings()
        cred = _credential(s)
        if cred is None and os.getenv("FIRESTORE_EMULATOR_HOST"):
            # 에뮬레이터는 인증을 보지 않는다 — Admin SDK 대신 같은 클라이언트를 익명 자격으로 연다
            from google.cloud import firestore as gcf
            _db = gcf.Client(project=s.firebase_project_id or "demo-mission2", credentials=AnonymousCredentials())
            return _db
        if cred is None:
            raise AppError(503, "NOT_CONFIGURED",
                           "Firebase 자격 증명이 없습니다. FIREBASE_SERVICE_ACCOUNT_JSON 환경 변수를 설정해 주세요.")
        options = {"projectId": s.firebase_project_id} if s.firebase_project_id else None
        app = firebase_admin.initialize_app(cred, options) if not firebase_admin._apps else firebase_admin.get_app()
        _db = firestore.client(app)
        return _db


def is_configured() -> bool:
    s = get_settings()
    return bool(s.firebase_service_account_json or s.firebase_service_account_path or os.getenv("FIRESTORE_EMULATOR_HOST"))
