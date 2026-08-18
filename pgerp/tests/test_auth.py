"""Tests for Auth module."""
import pytest
import sys
import os

# Add app to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from core.auth import User, Company, Session, hash_password, verify_password, generate_token


class TestPasswordHashing:
    def test_hash_returns_hash_and_salt(self):
        h, s = hash_password("test123")
        assert h is not None
        assert s is not None
        assert len(h) == 64  # SHA-256 hex
    
    def test_verify_correct_password(self):
        h, s = hash_password("mypassword")
        assert verify_password("mypassword", h, s) is True
    
    def test_verify_wrong_password(self):
        h, s = hash_password("mypassword")
        assert verify_password("wrong", h, s) is False
    
    def test_different_salts_different_hashes(self):
        h1, s1 = hash_password("same")
        h2, s2 = hash_password("same")
        assert h1 != h2
        assert s1 != s2


class TestTokenGeneration:
    def test_token_is_string(self):
        t = generate_token()
        assert isinstance(t, str)
    
    def test_token_is_unique(self):
        t1 = generate_token()
        t2 = generate_token()
        assert t1 != t2
    
    def test_token_length(self):
        t = generate_token()
        assert len(t) > 20


class TestUserModel:
    def test_create_user(self, db_conn):
        user = User.create(db_conn, "test@example.com", "pass123", "Test User", "admin", company_id=1)
        assert user.id is not None
        assert user.email == "test@example.com"
    
    def test_authenticate(self, db_conn):
        User.create(db_conn, "auth@test.com", "secret", "Auth Test", "user", company_id=1)
        user = User.authenticate(db_conn, "auth@test.com", "secret")
        assert user is not None
        assert user.email == "auth@test.com"
    
    def test_authenticate_wrong_password(self, db_conn):
        User.create(db_conn, "auth2@test.com", "secret", "Auth Test 2", "user", company_id=1)
        user = User.authenticate(db_conn, "auth2@test.com", "wrong")
        assert user is None
