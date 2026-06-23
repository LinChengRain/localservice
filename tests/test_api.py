def test_api_apps(client):
    response = client.get('/api/apps')
    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data, list)


def test_api_apps_grouped(client):
    response = client.get('/api/apps/grouped')
    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data, list)


def test_api_apps_pagination(client):
    response = client.get('/api/apps?page=1&per_page=5')
    assert response.status_code == 200
    data = response.get_json()
    assert 'items' in data
    assert 'total' in data
    assert 'page' in data
    assert 'per_page' in data
