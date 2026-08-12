"""
ARES User & UserRole Data Models
"""

from flask_login import UserMixin


class UserRole:
    def __init__(self, name, permissions):
        self.name = name
        self.permissions = permissions

    def __getattr__(self, name):
        if name in self.permissions:
            return bool(self.permissions[name])
        raise AttributeError(f"'UserRole' object has no attribute '{name}'")

    def __str__(self):
        return self.name


class User(UserMixin):
    def __init__(self, username, role_id, role_name, permissions):
        self.id = username
        self.username = username
        self.role_id = role_id
        self.role_name = role_name
        self.role = UserRole(role_name, permissions)
        self.permissions = permissions  # dict: {permission_flag: bool}

    def has_permission(self, permission_name):
        return bool(self.permissions.get(permission_name, False))
