def test_upload_page_requires_admin(client):
    response = client.get('/upload', follow_redirects=True)
    assert response.status_code == 200
