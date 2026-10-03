from django.contrib.auth.backends import ModelBackend


class AdminModelBackend(ModelBackend):
    # Keep the backend path for compatibility with existing local sessions/tests.
    # Authorization inside /admin/ is separate from portal authentication.
    def user_can_authenticate(self, user):
        from .access import is_operator
        return super().user_can_authenticate(user) and is_operator(user)
