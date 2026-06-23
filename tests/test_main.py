def test_index(client):
    response = client.get('/')
    assert response.status_code == 200
    assert '应用分发' in response.data.decode()


def test_health(client):
    response = client.get('/health')
    assert response.status_code == 200
    data = response.get_json()
    assert data['status'] == 'ok'


def test_install_nonexistent(client):
    response = client.get('/install/99999')
    assert response.status_code == 302
