"""
Unit & Integration Test: Flask Web Routes & Endpoint Responses
"""

import unittest
from app import app


class TestRoutes(unittest.TestCase):

    def setUp(self):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        self.client = app.test_client()

    def test_login_page_get(self):
        response = self.client.get('/login')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'html', response.data.lower())

    def test_unauthenticated_access_redirects(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 302)  # Redirects to /login

    def test_api_login_invalid_credentials(self):
        response = self.client.post('/api/login', data={
            'username': 'invalid_user',
            'password': 'wrong_password'
        })
        self.assertEqual(response.status_code, 401)
        self.assertIn(b'error', response.data)

    def test_api_login_valid_admin(self):
        response = self.client.post('/api/login', data={
            'username': 'admin',
            'password': 'admin123'
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'authenticated', response.data)


if __name__ == '__main__':
    unittest.main()
