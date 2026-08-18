from unittest.mock import AsyncMock

import pytest

from app.core import CHAT_KIND, encrypt_secret
from app.enums import ChatProvider
from app.models import ProviderConfig
from app.services.provider_config import ProviderConfigService


def _row(*, user_id, provider, api_key, active):
    return ProviderConfig(
        user_id=user_id,
        kind=CHAT_KIND,
        provider=provider,
        model="some-model",
        fallback_model=None,
        base_url="https://example.test",
        encrypted_api_key=encrypt_secret(api_key) if api_key else None,
        active=active,
    )


@pytest.mark.asyncio
async def test_global_default_api_key_is_never_handed_to_another_user():
    """A global default row's API key belongs to no one; a user who hasn't
    configured their own provider must get an empty key, not the shared
    admin credential -- even though they inherit the provider/model/active
    shape from the global row."""
    service = ProviderConfigService()
    admin_key_row = _row(
        user_id=None, provider=ChatProvider.GEMINI.value, api_key="admin-secret-key", active=True
    )
    service.provider_configs.list_all = AsyncMock(return_value=[admin_key_row])

    await service.load_from_db(db=object(), user_id=999)

    resolved = service.chat_configs[ChatProvider.GEMINI]
    assert resolved.api_key == ""
    assert resolved.active is True  # shape (provider/active) still inherited


@pytest.mark.asyncio
async def test_users_own_row_keeps_its_own_api_key():
    service = ProviderConfigService()
    own_row = _row(
        user_id=999, provider=ChatProvider.GEMINI.value, api_key="users-own-key", active=True
    )
    service.provider_configs.list_all = AsyncMock(return_value=[own_row])

    await service.load_from_db(db=object(), user_id=999)

    resolved = service.chat_configs[ChatProvider.GEMINI]
    assert resolved.api_key == "users-own-key"


@pytest.mark.asyncio
async def test_saving_a_new_users_key_creates_their_own_row_not_the_global_one():
    """Regression test: _get_row used to fall back to the global default row
    when a user had no row of their own, so saving a user's API key silently
    overwrote the shared global row instead of creating a per-user override
    -- and the key then vanished on reload (isolation correctly refuses to
    hand a global row's key to a specific user)."""
    service = ProviderConfigService()
    global_row = _row(
        user_id=None, provider=ChatProvider.GROQ.value, api_key=None, active=True
    )

    async def fake_get_own(db, kind, provider, user_id):
        # No row owned by this user yet -- only the global default exists.
        return None

    service.provider_configs.get_own = fake_get_own
    service.provider_configs.add = AsyncMock()
    service.provider_configs.commit = AsyncMock()

    service.chat_configs[ChatProvider.GROQ].api_key = "the-users-new-key"
    await service._save_all_chat(db=object(), user_id=999)

    added_rows = [call.args[1] for call in service.provider_configs.add.await_args_list]
    groq_rows = [row for row in added_rows if row.provider == ChatProvider.GROQ.value]
    assert len(groq_rows) == 1
    assert groq_rows[0].user_id == 999
    assert global_row.encrypted_api_key is None  # global row untouched
