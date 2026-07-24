import os
import tempfile
import unittest
from decimal import Decimal

from app import create_app
from app.extensions import db
from app.models import Product, User


class ConsoleReportingTestCase(unittest.TestCase):
    def run(self, result=None):
        if result is None:
            return super().run(result)

        description = self.shortDescription() or self._testMethodName
        print(f"\n[TEST] {description}")
        start_failures = len(result.failures)
        start_errors = len(result.errors)
        start_skips = len(getattr(result, "skipped", []))

        outcome = super().run(result)

        if len(result.errors) > start_errors:
            print(f"[RESULT] ERROR - {description}")
        elif len(result.failures) > start_failures:
            print(f"[RESULT] FAIL - {description}")
        elif len(getattr(result, "skipped", [])) > start_skips:
            print(f"[RESULT] SKIP - {description}")
        else:
            print(f"[RESULT] PASS - {description}")
        return outcome

    def log_step(self, message):
        print(f"  - {message}")


class PlatformTestCase(ConsoleReportingTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = os.path.join(self.temp_dir.name, "test.db")
        database_uri = f"sqlite:///{database_path.replace(os.sep, '/')}"
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret",
                "WTF_CSRF_ENABLED": False,
                "SQLALCHEMY_DATABASE_URI": database_uri,
                "UPLOAD_FOLDER": self.temp_dir.name,
                "RATELIMIT_ENABLED": False,
                "PRODUCT_REPORT_THRESHOLD": 1,
                "USER_REPORT_THRESHOLD": 1,
                "ADMIN_USERNAME": "admin",
                "ADMIN_PASSWORD": "AdminPass123!",
                "SOCKETIO_CORS_ALLOWED_ORIGINS": ["http://localhost"],
            }
        )
        self.client = self.app.test_client()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()
        self.temp_dir.cleanup()

    def register(self, username, display_name=None, password="Password123!"):
        return self.client.post(
            "/auth/register",
            data={
                "username": username,
                "display_name": display_name or username,
                "password": password,
                "password_confirm": password,
                "bio": "테스트 사용자입니다.",
            },
            follow_redirects=True,
        )

    def login(self, username, password="Password123!"):
        return self.client.post(
            "/auth/login",
            data={"username": username, "password": password},
            follow_redirects=True,
        )

    def logout(self):
        return self.client.get("/auth/logout", follow_redirects=True)

    def test_register_login_and_create_product(self):
        """Verifies signup, login, product creation, and product search."""
        self.log_step("Create seller account and sign in.")
        self.register("seller1", "판매자")
        response = self.login("seller1")
        self.assertIn("Tiny Second-hand", response.get_data(as_text=True))

        self.log_step("Create a product and confirm success response.")
        response = self.client.post(
            "/products/new",
            data={
                "title": "테스트 노트북",
                "category": "전자기기",
                "description": "상태가 좋은 중고 노트북입니다. 테스트용 설명을 충분히 작성합니다.",
                "price": "350000",
                "status": "available",
            },
            follow_redirects=True,
        )

        self.assertIn("상품이 등록되었습니다.", response.get_data(as_text=True))
        self.log_step("Search products and verify the new listing appears.")
        search_response = self.client.get("/products/?q=노트북")
        self.assertIn("테스트 노트북", search_response.get_data(as_text=True))

    def test_report_blocks_product(self):
        """Verifies a reported product is auto-blocked at threshold."""
        self.log_step("Prepare seller and reporter accounts.")
        self.register("seller2", "판매자2")
        self.register("reporter1", "신고자1")

        self.log_step("Seller creates the product to be reported.")
        self.login("seller2")
        self.client.post(
            "/products/new",
            data={
                "title": "문제 상품",
                "category": "기타",
                "description": "신고 테스트용 상품 설명입니다. 충분한 길이의 텍스트를 포함합니다.",
                "price": "10000",
                "status": "available",
            },
            follow_redirects=True,
        )
        self.logout()

        with self.app.app_context():
            product = Product.query.filter_by(title="문제 상품").first()
            self.assertIsNotNone(product)
            assert product is not None
            product_id = product.id

        self.log_step("Reporter submits a report and checks auto-blocking.")
        self.login("reporter1")
        response = self.client.post(
            f"/reports/new/product/{product_id}",
            data={"reason": "사기성 게시글로 의심되며 정상 거래가 어려워 보입니다."},
            follow_redirects=True,
        )

        self.assertIn("자동 차단", response.get_data(as_text=True))
        with self.app.app_context():
            product = db.session.get(Product, product_id)
            assert product is not None
            self.assertTrue(product.is_blocked)

    def test_wallet_transfer_updates_balances(self):
        """Verifies wallet transfer updates both balances correctly."""
        self.log_step("Create two users for the transfer scenario.")
        with self.app.app_context():
            alice = User()
            alice.username = "alice01"
            alice.display_name = "앨리스"
            alice.bio = "테스트 사용자"
            alice.set_password("Password123!")

            bob = User()
            bob.username = "bob0001"
            bob.display_name = "밥"
            bob.bio = "테스트 사용자"
            bob.set_password("Password123!")
            db.session.add_all([alice, bob])
            db.session.commit()

        self.log_step("Send transfer request and confirm success response.")
        self.login("alice01")
        response = self.client.post(
            "/wallet/",
            data={
                "recipient_username": "bob0001",
                "amount": "5000",
                "note": "거래 대금",
            },
            follow_redirects=True,
        )

        self.assertIn("송금이 완료되었습니다.", response.get_data(as_text=True))
        self.log_step("Verify sender and recipient balances are updated.")
        with self.app.app_context():
            alice = User.query.filter_by(username="alice01").first()
            bob = User.query.filter_by(username="bob0001").first()
            assert alice is not None
            assert bob is not None
            self.assertEqual(Decimal(str(alice.balance)), Decimal("95000.00"))
            self.assertEqual(Decimal(str(bob.balance)), Decimal("105000.00"))

    def test_admin_dashboard_accessible(self):
        """Verifies the default admin can access the admin dashboard."""
        self.log_step("Sign in with the default admin account.")
        self.login("admin", "AdminPass123!")
        self.log_step("Check dashboard response code and title.")
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("관리자 대시보드", response.get_data(as_text=True))

    def test_user_withdrawal_hides_account_and_products(self):
        """Verifies withdrawal hides the user account and products."""
        self.log_step("Create a product under the account to withdraw.")
        self.register("byeuser1", "탈퇴예정")
        self.login("byeuser1")
        self.client.post(
            "/products/new",
            data={
                "title": "탈퇴 전 상품",
                "category": "생활",
                "description": "회원 탈퇴 시 상품이 함께 내려가는지 확인하는 테스트 데이터입니다.",
                "price": "12000",
                "status": "available",
            },
            follow_redirects=True,
        )

        with self.app.app_context():
            user = User.query.filter_by(username="byeuser1").first()
            self.assertIsNotNone(user)
            assert user is not None
            user_id = user.id
            product = Product.query.filter_by(seller_id=user_id).first()
            self.assertIsNotNone(product)
            assert product is not None
            product_id = product.id

        self.log_step("Submit withdrawal request and confirm success response.")
        response = self.client.post(
            "/profile/withdraw",
            data={"password": "Password123!", "confirmation": "탈퇴"},
            follow_redirects=True,
        )

        self.assertIn("회원 탈퇴가 완료되었습니다.", response.get_data(as_text=True))
        with self.app.app_context():
            withdrawn_user = db.session.get(User, user_id)
            withdrawn_product = db.session.get(Product, product_id)
            assert withdrawn_user is not None
            assert withdrawn_product is not None
            self.assertTrue(withdrawn_user.is_deleted)
            self.assertTrue(withdrawn_user.is_suspended)
            self.assertEqual(withdrawn_user.display_name, "탈퇴한 사용자")
            self.assertTrue(withdrawn_product.is_deleted)
            self.assertTrue(withdrawn_product.is_blocked)

        self.log_step("Verify withdrawn account is hidden and login is blocked.")
        users_page = self.client.get("/users")
        self.assertNotIn("byeuser1", users_page.get_data(as_text=True))

        login_response = self.login("byeuser1")
        self.assertIn(
            "아이디 또는 비밀번호가 올바르지 않습니다.",
            login_response.get_data(as_text=True),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
