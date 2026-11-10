"""Isolated workspace integration server; never touches installed services or user queues.

Loads either edition's real Django workspace/auth views and the real Jobs API,
engine snapshot code and SQLite journal. The transport seam calls that API in
process instead of the installed Windows control pipe. Historical QA rows are
seeded explicitly; these are not downloads or evidence of installed acceptance.
"""

import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys
from urllib.parse import parse_qsl, urlsplit
from wsgiref.simple_server import make_server


def serve(repo, state, port):
    state.mkdir(parents=True, exist_ok=True)
    os.environ.update(TEMP=str(state), TMP=str(state))
    host = Path(__file__).resolve().parents[2]
    sys.path[:0] = [str(repo / "Tlamatini"), str(host / "workers/torrent")]
    sys.path.append(str(host / "artifacts/jobs-runtime"))
    from django.apps import AppConfig
    from django.conf import settings

    settings.configure(
        SECRET_KEY="isolated-workspace-table-test-only",
        DEBUG=True,
        ALLOWED_HOSTS=["127.0.0.1"],
        ROOT_URLCONF=__name__,
        LANGUAGE_CODE="es" if repo.name.endswith("Spanish") else "en",
        INSTALLED_APPS=[
            "django.contrib.auth",
            "django.contrib.contenttypes",
            "django.contrib.sessions",
            AppConfig("agent", importlib.import_module("agent")),
        ],
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": str(state / "accounts.sqlite"),
            }
        },
        MIDDLEWARE=[
            "django.contrib.sessions.middleware.SessionMiddleware",
            "django.middleware.csrf.CsrfViewMiddleware",
            "django.contrib.auth.middleware.AuthenticationMiddleware",
        ],
        TEMPLATES=[
            {
                "BACKEND": "django.template.backends.django.DjangoTemplates",
                "OPTIONS": {
                    "loaders": [
                        (
                            "django.template.loaders.locmem.Loader",
                            {
                                "login.html": '<title>Torrenter table verification — sign in</title><body style="background:#14232d;color:white;font:20px Segoe UI;padding:3rem">'
                                "<h1>Isolated workspace verification</h1><p>Test accounts · source edition</p>"
                                '<form method="post">{% csrf_token %}{{ form.as_p }}<button>Sign in</button></form></body>'
                            },
                        )
                    ]
                },
            }
        ],
        DEFAULT_AUTO_FIELD="django.db.models.BigAutoField",
        LOGIN_URL="/login/",
        USE_TZ=True,
        PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    )
    import django

    django.setup()
    from django.core.management import call_command
    from django.db import connection
    from django.contrib.auth.models import User
    from django.contrib.auth.views import LoginView, LogoutView
    from django.urls import path
    from django.core.wsgi import get_wsgi_application
    from agent.models import TorrenterProfile
    from agent import torrenter_views
    from agent.torrenter_bridge import profile_for
    from api import Api
    from engine import Engine
    from storage import Journal, Problem, packed

    call_command("migrate", "auth", verbosity=0)
    call_command("migrate", "sessions", verbosity=0)
    if TorrenterProfile._meta.db_table not in connection.introspection.table_names():
        with connection.schema_editor() as editor:
            editor.create_model(TorrenterProfile)
    journal = Journal(state / "queue")
    engine = Engine(journal, development=True)
    api = Api(journal, engine)
    profiles = {}
    for name, count in (("table-review", 263), ("table-other", 12)):
        user, _ = User.objects.get_or_create(username=name)
        user.set_password("Workspace-test-only-2026")
        user.save()
        profile = profile_for(user.pk)
        profiles[name] = profile
        if journal.db.execute(
            "SELECT count(*) FROM jobs WHERE owner=?", (profile,)
        ).fetchone()[0]:
            continue
        for index in range(count):
            title = f"QA Atlas {index + 1} — résumé.pdf"
            name_bytes = title.encode()
            raw = (
                b"d4:infod6:lengthi8e4:name"
                + str(len(name_bytes)).encode()
                + b":"
                + name_bytes
                + b"12:piece lengthi16384e6:pieces20:"
                + hashlib.sha1(b"testdata").digest()
                + b"7:privatei1eee"
            )
            options = dict(
                category="Science" if index % 2 else "Art",
                tags=["review", "odd" if index % 2 else "even"],
                queue_position=count - index,
                resume_on_boot=False,
                seed_after_completion=False,
                download_limit=0,
                upload_limit=0,
                priorities={"0": 4},
            )
            snapshot = dict(
                name=title,
                selected_bytes=(index + 1) * 1024,
                verified_bytes=(index % 11) * ((index + 1) * 1024) / 10,
                ratio=index / 10,
                availability=None if index % 7 == 0 else index / 5,
                eta_seconds=None if index % 5 == 0 else index * 40,
                tracker_hosts=["qa.invalid"],
            )
            job_id = hashlib.sha256((profile + str(index)).encode()).hexdigest()[:32]
            journal.db.execute(
                "INSERT INTO jobs(id,owner,metainfo,selection,options,desired,snapshot,created,completed) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    job_id,
                    profile,
                    raw,
                    "[0]",
                    packed(options),
                    "paused" if index % 2 else "stopped",
                    packed(snapshot),
                    1700000000 + index,
                    1700100000 + index if index % 3 == 0 else None,
                ),
            )
    journal.db.commit()
    # Deliberately failed source-only QA job for visible recovery controls.
    failed_id = hashlib.sha256((profiles['table-review'] + '4').encode()).hexdigest()[:32]
    journal.db.execute("UPDATE jobs SET desired='running' WHERE id=?", (failed_id,))
    engine.failures[failed_id] = 'QA disk verification failure; recheck required'
    journal.db.commit()
    from django.contrib.auth import authenticate

    assert (
        authenticate(username="table-review", password="Workspace-test-only-2026")
        is not None
    ), "Isolated login setup failed"

    def session(profile):
        result = journal.issue(profile, "read submit control remove erase", 3600)
        journal.db.commit()
        return result["access_token"]

    def request(method, route, body=None, *, bearer=None, key=None, revision=None):
        url = urlsplit(route)
        try:
            result = api.dispatch(
                dict(
                    method=method,
                    path=url.path,
                    query=dict(parse_qsl(url.query)),
                    body=body,
                    authorization="Bearer " + (bearer or ""),
                    key=key,
                    # Match client.request's HTTP If-Match encoding at this seam.
                    revision=f'"{revision}"' if revision is not None else None,
                )
            )
            journal.db.commit()
            return result[0], torrenter_views.client.publication_status(result[1])
        except Problem as exc:
            journal.db.rollback()
            raise torrenter_views.client.JobsHttpError(exc.status, str(exc)) from exc

    torrenter_views.client.session = session
    torrenter_views.client.request = request
    global urlpatterns
    urlpatterns = [
        path("login/", LoginView.as_view(template_name="login.html")),
        path("logout/", LogoutView.as_view(next_page="/login/")),
        path("agent/torrenter/workspace/", torrenter_views.workspace),
        path("agent/torrenter/workspace/session/", torrenter_views.workspace_session),
        path(
            "agent/torrenter/workspace/api/v1/<path:route>",
            torrenter_views.workspace_api,
        ),
        path("agent/torrenter/workspace/<str:asset>", torrenter_views.workspace_asset),
    ]
    (state / "identity.json").write_text(json.dumps(profiles), encoding="utf-8")
    print(
        f"READY {repo.name}: http://127.0.0.1:{port}/agent/torrenter/workspace/ — isolated historical QA rows",
        flush=True,
    )
    try:
        with make_server("127.0.0.1", port, get_wsgi_application()) as server:
            server.serve_forever()
    finally:
        engine.close()
        journal.db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--port", required=True, type=int)
    args = parser.parse_args()
    serve(args.repo, args.state, args.port)
