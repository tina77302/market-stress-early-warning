import secrets
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest

from src.admin.create_admin import main
from src.paper.admin import provision_admin, record_admin_activity
from src.paper.auth import password_matches
from src.paper.store import database


@pytest.fixture
def environment(tmp_path, monkeypatch):
    monkeypatch.setenv('PAPER_DB_PATH',str(tmp_path/'multiple.sqlite3'))
    monkeypatch.delenv('ADMIN_EMAIL',raising=False)
    monkeypatch.delenv('ADMIN_PASSWORD',raising=False)


def test_independent_admins_and_idempotent_audit(environment):
    first,second=secrets.token_urlsafe(32),secrets.token_urlsafe(32)
    assert provision_admin('first@example.invalid',first)=='created'
    assert provision_admin('second@example.invalid',second)=='created'
    assert provision_admin('first@example.invalid',second)=='already_exists'
    with database() as db:
        rows=db.execute('SELECT * FROM users ORDER BY id').fetchall()
        assert len(rows)==2 and all(row['role']=='admin' for row in rows)
        assert password_matches(first,rows[0]['password_hash'])
        assert password_matches(second,rows[1]['password_hash'])
        assert not password_matches(second,rows[0]['password_hash'])
        assert db.execute('SELECT COUNT(*) FROM portfolios').fetchone()[0]==4
        events=db.execute('SELECT * FROM admin_activity').fetchall()
        assert len(events)==2
        assert all(row['action']=='admin.bootstrap_created' and row['admin_user_id']==row['target_user_id'] for row in events)
        assert first not in str([dict(row) for row in events])
        with pytest.raises(sqlite3.IntegrityError):db.execute('DELETE FROM admin_activity')
        with pytest.raises(sqlite3.IntegrityError):db.execute("UPDATE admin_activity SET action='changed'")


def test_final_admin_guards_and_concurrent_demotion(environment):
    provision_admin('first@example.invalid',secrets.token_urlsafe(32))
    with database() as db:
        with pytest.raises(sqlite3.IntegrityError,match='final administrator'):db.execute("UPDATE users SET role='user' WHERE id=1")
        with pytest.raises(sqlite3.IntegrityError,match='final administrator'):db.execute('DELETE FROM users WHERE id=1')
    provision_admin('second@example.invalid',secrets.token_urlsafe(32))
    def demote(user_id):
        try:
            with database() as db:
                db.execute("UPDATE users SET role='user' WHERE id=?",(user_id,))
                db.commit()
            return 'changed'
        except sqlite3.IntegrityError:return 'blocked'
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(demote,[1,2]))
    assert sorted(results)==['blocked','changed']
    with database() as db:assert db.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0]==1


def test_delete_an_admin_when_another_remains(environment):
    provision_admin('first@example.invalid',secrets.token_urlsafe(32))
    provision_admin('second@example.invalid',secrets.token_urlsafe(32))
    with database() as db:
        # Clear owned empty portfolios only in this isolated fixture; no deletion API exists.
        db.execute('DELETE FROM snapshots WHERE portfolio_id IN (SELECT id FROM portfolios WHERE user_id=1)')
        db.execute('DELETE FROM portfolios WHERE user_id=1')
        db.execute('DELETE FROM users WHERE id=1');db.commit()
        assert db.execute('SELECT COUNT(*) FROM admin_activity').fetchone()[0]==2
        with pytest.raises(sqlite3.IntegrityError,match='final administrator'):db.execute('DELETE FROM users WHERE id=2')


def test_secure_cli_and_cancelled_prompts(environment,caplog,capsys):
    password=secrets.token_urlsafe(32)
    with patch('src.admin.create_admin.sys.stdin.isatty',return_value=True),patch('src.admin.create_admin.getpass.getpass',side_effect=[password,password]) as prompt:
        assert main(['--email','first@example.invalid'])==0
        assert prompt.call_count==2
    captured=capsys.readouterr()
    assert password not in captured.out+captured.err+caplog.text
    with patch('src.admin.create_admin.sys.stdin.isatty',return_value=False):assert main(['--email','second@example.invalid'])==1
    with patch('src.admin.create_admin.sys.stdin.isatty',return_value=True),patch('src.admin.create_admin.getpass.getpass',side_effect=[password,'different']):assert main(['--email','second@example.invalid'])==1
    with database() as db:assert db.execute('SELECT COUNT(*) FROM users').fetchone()[0]==1
    with pytest.raises(SystemExit):main(['--email','x@example.invalid','--password',password])
    captured=capsys.readouterr()
    assert password not in captured.out+captured.err


def test_audit_actor_authorization(environment):
    provision_admin('first@example.invalid',secrets.token_urlsafe(32))
    provision_admin('second@example.invalid',secrets.token_urlsafe(32))
    with database() as db:
        db.execute("UPDATE users SET role='user' WHERE id=2");db.commit()
        with pytest.raises(RuntimeError):record_admin_activity(db,2,'user.reviewed',1)
        with pytest.raises(ValueError):record_admin_activity(db,1,'free form request credentials',2)
        record_admin_activity(db,1,'user.reviewed',2);db.commit()
        assert db.execute('SELECT COUNT(*) FROM admin_activity').fetchone()[0]==3
