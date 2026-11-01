import os

from locust import HttpUser, between, task


class SessionLenderUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        self.logged_in = False
        username = os.getenv('LOCUST_USERNAME')
        password = os.getenv('LOCUST_PASSWORD')
        self.client.get('/login/')
        if not username or not password:
            return

        csrf_token = self.client.cookies.get('csrftoken', '')
        response = self.client.post(
            '/login/',
            data={'nickname': username, 'password': password},
            headers={'X-CSRFToken': csrf_token},
        )
        self.logged_in = response.ok and 'login' not in response.url

    @task(4)
    def view_feed(self):
        if self.logged_in:
            self.client.get('/')

    @task(3)
    def view_people(self):
        if self.logged_in:
            self.client.get('/people/')

    @task(2)
    def view_rooms(self):
        if self.logged_in:
            self.client.get('/rooms/')

    @task(2)
    def view_chats(self):
        if self.logged_in:
            self.client.get('/messages/')

    @task(1)
    def view_profile(self):
        if self.logged_in:
            self.client.get('/profile/')

    @task(1)
    def view_login(self):
        self.client.get('/login/')

    @task(1)
    def view_register(self):
        self.client.get('/register/')
