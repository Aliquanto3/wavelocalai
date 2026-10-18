"""Tests de scripts/sync_slm_results.py, sans réseau (transport simulé)."""

import hashlib
import json
from datetime import datetime, timezone

import pytest

from scripts import sync_slm_results as sync_mod

REPO = "Aliquanto3/slm-quality-bench"
TAG = "v1.2.0"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
ASSET_URL = f"https://github.com/{REPO}/releases/download/{TAG}/slm-quality-results.json"
SCHEMA_URL = f"https://raw.githubusercontent.com/{REPO}/{TAG}/docs/schemas/qb.results-1.schema.json"

# Petit schéma de test, pas le schéma réel de slm-quality-bench.
TEST_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["models", "results"],
    "properties": {
        "models": {"type": "array"},
        "results": {"type": "array", "items": {"type": "object", "required": ["model"]}},
    },
}
VALID = {"models": [{"id": "a"}], "results": [{"model": "a"}]}
INVALID = {"models": [], "results": [{"score": 1}]}


def _bytes(obj) -> bytes:
    # Mise en forme volontairement non canonique : les octets doivent rester tels quels.
    return json.dumps(obj, indent=3, ensure_ascii=False).encode("utf-8") + b"\n\n"


def _release(with_asset: bool = True) -> bytes:
    assets = (
        [{"name": "slm-quality-results.json", "browser_download_url": ASSET_URL}]
        if with_asset
        else [{"name": "autre.txt", "browser_download_url": "https://exemple.invalid/x"}]
    )
    return json.dumps(
        {
            "tag_name": TAG,
            "html_url": f"https://github.com/{REPO}/releases/tag/{TAG}",
            "assets": assets,
        }
    ).encode()


class FakeTransport:
    """Transport simulé : url -> (code, corps) ; enregistre les appels."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, url, headers):
        self.calls.append((url, dict(headers)))
        return self.routes.get(url, (404, b"introuvable"))


def _routes(payload=VALID, with_asset=True):
    return {
        API_URL: (200, _release(with_asset)),
        ASSET_URL: (200, _bytes(payload)),
        SCHEMA_URL: (200, json.dumps(TEST_SCHEMA).encode()),
    }


def _run(tmp_path, routes, *, check=False, env=None):
    transport = FakeTransport(routes)
    code = sync_mod.sync(
        REPO,
        check=check,
        transport=transport,
        out_dir=tmp_path / "snap",
        env={} if env is None else env,
        now=lambda: datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc),
    )
    return code, transport


def test_release_absente(tmp_path, capsys):
    code, _ = _run(tmp_path, {})
    assert code == 0
    assert "Aucune release" in capsys.readouterr().out
    assert not (tmp_path / "snap").exists()


def test_asset_absent(tmp_path, capsys):
    code, transport = _run(tmp_path, _routes(with_asset=False))
    assert code == 0
    assert "ne contient pas encore l'asset" in capsys.readouterr().out
    assert not (tmp_path / "snap").exists()
    assert [url for url, _ in transport.calls] == [API_URL]


def test_fichier_valide_ecrit_octets_et_source(tmp_path):
    code, _ = _run(tmp_path, _routes())
    assert code == 0
    snap = tmp_path / "snap"
    published = _bytes(VALID)
    assert (snap / "slm-quality-results.json").read_bytes() == published
    source = json.loads((snap / "SOURCE.json").read_text(encoding="utf-8"))
    assert source["tag"] == TAG
    assert source["asset_url"] == ASSET_URL
    assert source["asset_sha256"] == hashlib.sha256(published).hexdigest()
    assert source["schema"] == "qb.results-1"
    assert source["schema_url"] == SCHEMA_URL
    assert source["schema_sha256"] == hashlib.sha256(json.dumps(TEST_SCHEMA).encode()).hexdigest()
    assert source["fetched_at"] == "2026-10-18T12:00:00+00:00"


def test_fichier_inchange_dit_deja_a_jour(tmp_path, capsys):
    _run(tmp_path, _routes())
    source_path = tmp_path / "snap" / "SOURCE.json"
    before = source_path.read_text(encoding="utf-8")
    capsys.readouterr()

    code, _ = _run(tmp_path, _routes())
    assert code == 0
    assert "déjà à jour" in capsys.readouterr().out
    assert source_path.read_text(encoding="utf-8") == before


def test_fichier_modifie_localement_est_reecrit(tmp_path):
    _run(tmp_path, _routes())
    results = tmp_path / "snap" / "slm-quality-results.json"
    results.write_bytes(b"{}")
    _run(tmp_path, _routes())
    assert results.read_bytes() == _bytes(VALID)


def test_fichier_invalide_n_ecrit_rien(tmp_path, capsys):
    with pytest.raises(sync_mod.SyncError) as excinfo:
        _run(tmp_path, _routes(payload=INVALID))
    assert "Validation échouée" in str(excinfo.value)
    assert "Rien n'a été écrit" in str(excinfo.value)
    assert not (tmp_path / "snap").exists()


def test_main_renvoie_1_et_message_sur_stderr(monkeypatch, capsys):
    def boom(repo, check=False):
        raise sync_mod.SyncError("validation en échec")

    monkeypatch.setattr(sync_mod, "sync", boom)
    assert sync_mod.main(["--repo", REPO]) == 1
    assert "Erreur : validation en échec" in capsys.readouterr().err


def test_main_transmet_repo_et_check(monkeypatch):
    vus = {}

    def faux_sync(repo, check=False):
        vus.update(repo=repo, check=check)
        return 0

    monkeypatch.setattr(sync_mod, "sync", faux_sync)
    assert sync_mod.main(["--repo", "a/b", "--check"]) == 0
    assert vus == {"repo": "a/b", "check": True}


def test_check_n_ecrit_rien(tmp_path, capsys):
    code, _ = _run(tmp_path, _routes(), check=True)
    assert code == 0
    out = capsys.readouterr().out
    assert "Mise à jour disponible" in out
    assert not (tmp_path / "snap").exists()


def test_schema_choisi_selon_le_champ_du_fichier(tmp_path):
    payload = dict(VALID, schema="qb.results/2")
    routes = _routes(payload=payload)
    schema_v2 = SCHEMA_URL.replace("qb.results-1", "qb.results-2")
    routes[schema_v2] = routes.pop(SCHEMA_URL)
    code, transport = _run(tmp_path, routes)
    assert code == 0
    assert schema_v2 in [url for url, _ in transport.calls]


def test_version_de_schema_inconnue_refusee(tmp_path):
    payload = dict(VALID, schema="../../autre")
    with pytest.raises(sync_mod.SyncError, match="non reconnue"):
        _run(tmp_path, _routes(payload=payload))
    assert not (tmp_path / "snap").exists()


def test_schema_introuvable_n_ecrit_rien(tmp_path):
    routes = _routes()
    del routes[SCHEMA_URL]
    with pytest.raises(sync_mod.SyncError, match="JSON Schema impossible"):
        _run(tmp_path, routes)
    assert not (tmp_path / "snap").exists()


def test_erreur_http_de_l_api(tmp_path):
    with pytest.raises(sync_mod.SyncError, match="HTTP 500"):
        _run(tmp_path, {API_URL: (500, b"")})


def test_github_output_changed_true_puis_false(tmp_path):
    out = tmp_path / "github_output.txt"
    env = {"GITHUB_OUTPUT": str(out)}
    _run(tmp_path, _routes(), env=env)
    assert out.read_text(encoding="utf-8").splitlines() == ["changed=true", f"version={TAG}"]

    out.write_text("", encoding="utf-8")
    _run(tmp_path, _routes(), env=env)
    assert out.read_text(encoding="utf-8").splitlines() == ["changed=false", f"version={TAG}"]


def test_github_output_sans_release(tmp_path):
    out = tmp_path / "github_output.txt"
    _run(tmp_path, {}, env={"GITHUB_OUTPUT": str(out)})
    assert out.read_text(encoding="utf-8").splitlines() == ["changed=false", "version="]


def test_jeton_envoye_a_l_api_seulement(tmp_path):
    _, transport = _run(tmp_path, _routes(), env={"GITHUB_TOKEN": "secret"})
    headers = dict(transport.calls)
    assert headers[API_URL]["Authorization"] == "Bearer secret"
    assert "Authorization" not in headers[ASSET_URL]
    assert "Authorization" not in headers[SCHEMA_URL]


def test_tag_dangereux_refuse(tmp_path):
    release = json.dumps({"tag_name": "v1\nchanged=true", "assets": []}).encode()
    with pytest.raises(sync_mod.SyncError, match="Tag de release inutilisable"):
        _run(tmp_path, {API_URL: (200, release)})
