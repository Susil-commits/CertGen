import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_job_invalid_recipient(client: AsyncClient) -> None:
    """Test various invalid payloads fail schema validation with HTTP 422."""
    # Case 1: Empty recipients list
    res_empty = await client.post("/api/jobs/", json={"recipients": []})
    assert res_empty.status_code == 422

    # Case 2: Missing recipient name
    res_no_name = await client.post(
        "/api/jobs/",
        json={"recipients": [{"email": "noname@example.com"}]},
    )
    assert res_no_name.status_code == 422

    # Case 3: Empty string recipient name
    res_empty_name = await client.post(
        "/api/jobs/",
        json={"recipients": [{"name": ""}]},
    )
    assert res_empty_name.status_code == 422

    # Case 4: Missing recipients property completely
    res_no_body = await client.post("/api/jobs/", json={})
    assert res_no_body.status_code == 422

    # Case 5: Recipients is not a list
    res_invalid_type = await client.post(
        "/api/jobs/",
        json={"recipients": "not-a-list"},
    )
    assert res_invalid_type.status_code == 422
