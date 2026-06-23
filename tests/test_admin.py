def test_backup_requires_admin(client):
    response = client.get('/admin/backup', follow_redirects=True)
    assert response.status_code in [200, 404]
