from httpx import AsyncClient
from sqlalchemy import select

from aiso_core.models.beta_access_request import BetaAccessRequest


async def test_beta_access_request_saves_form_data_and_token(
    client: AsyncClient,
    db_session,
    beta_token_store: dict[str, str],
):
    response = await client.post(
        "/api/v1/beta/access-request",
        data={"email": "beta1@example.com", "extra_text": "Need access for QA"},
    )
    assert response.status_code == 201

    token = beta_token_store["beta1@example.com"]
    assert token

    result = await db_session.execute(
        select(BetaAccessRequest).where(BetaAccessRequest.email == "beta1@example.com")
    )
    request = result.scalar_one()
    assert request.extra_text == "Need access for QA"
    assert request.token_hash
    assert request.email_sent_at is not None


async def test_beta_access_request_updates_existing_email(
    client: AsyncClient,
    db_session,
    beta_token_store: dict[str, str],
):
    first = await client.post(
        "/api/v1/beta/access-request",
        data={"email": "beta2@example.com", "extra_text": "First request"},
    )
    assert first.status_code == 201
    first_token = beta_token_store["beta2@example.com"]

    second = await client.post(
        "/api/v1/beta/access-request",
        data={"email": "beta2@example.com", "extra_text": "Second request"},
    )
    assert second.status_code == 201
    second_token = beta_token_store["beta2@example.com"]

    assert first_token != second_token

    result = await db_session.execute(
        select(BetaAccessRequest).where(BetaAccessRequest.email == "beta2@example.com")
    )
    request = result.scalar_one()
    assert request.extra_text == "Second request"
    assert request.email_sent_at is not None
