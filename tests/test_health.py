async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_ready_when_redis_up(client):
    resp = await client.get("/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert body["components"]["redis"] is True


async def test_ready_when_redis_down(client, mock_cache):
    mock_cache.ping.side_effect = ConnectionError("redis down")
    resp = await client.get("/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["components"]["redis"] is False
