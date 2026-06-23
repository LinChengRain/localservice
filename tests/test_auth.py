def test_login_page(client):
    response = client.get('/auth/login')
    assert response.status_code == 200
    assert '登录' in response.data.decode()


def test_logout(client):
    response = client.get('/auth/logout', follow_redirects=True)
    assert response.status_code == 200
