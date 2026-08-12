"""
Unit Test: RBAC Models, Permission Flags & Forensic Logging
"""

import unittest
import os
from ares_app.security.models import User, UserRole
from ares_app.security.audit import log_security_event
from ares_app.config import STATIC_DIR


class TestSecurity(unittest.TestCase):

    def test_user_role_permissions(self):
        perms = {
            'delete_logs': True,
            'export_reports': True,
            'run_simulations': False
        }
        role = UserRole("admin", perms)
        self.assertTrue(role.delete_logs)
        self.assertTrue(role.export_reports)
        self.assertFalse(role.run_simulations)

        user = User("admin_user", 1, "admin", perms)
        self.assertTrue(user.has_permission("delete_logs"))
        self.assertFalse(user.has_permission("run_simulations"))
        self.assertFalse(user.has_permission("non_existent_perm"))

    def test_log_security_event(self):
        log_path = os.path.join(STATIC_DIR, 'security_audit.log')
        if os.path.exists(log_path):
            initial_size = os.path.getsize(log_path)
        else:
            initial_size = 0

        log_security_event("test_user", "UNIT_TEST_ACTION", "SUCCESS", "Testing audit logger")
        self.assertTrue(os.path.exists(log_path))
        new_size = os.path.getsize(log_path)
        self.assertGreater(new_size, initial_size)


if __name__ == '__main__':
    unittest.main()
