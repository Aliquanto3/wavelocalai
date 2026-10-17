"""Lanceur `uv run wavelocalai` : création de data/models.json et garde de la racine."""

import json

from src.app import launcher


def _catalog(root, models):
    (root / "config").mkdir()
    (root / "config" / "models_catalog.json").write_text(
        json.dumps({"_reference_machine": {}, "models": models}), encoding="utf-8"
    )


def test_ensure_models_json_cree_depuis_le_catalogue(tmp_path):
    _catalog(tmp_path, {"Granite 4.0 350M": {"ollama_tag": "granite4:350m"}})

    assert launcher.ensure_models_json(tmp_path) is True
    data = json.loads((tmp_path / "data" / "models.json").read_text(encoding="utf-8"))
    assert data == {"Granite 4.0 350M": {"ollama_tag": "granite4:350m"}}


def test_ensure_models_json_n_ecrase_jamais(tmp_path):
    _catalog(tmp_path, {"A": {}})
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "models.json").write_text('{"local": 1}', encoding="utf-8")

    assert launcher.ensure_models_json(tmp_path) is False
    assert (tmp_path / "data" / "models.json").read_text(encoding="utf-8") == '{"local": 1}'


def test_main_refuse_hors_du_depot(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(launcher, "ROOT", tmp_path)

    assert launcher.main([]) == 1
    assert "Racine du dépôt introuvable" in capsys.readouterr().err
    assert not (tmp_path / "data").exists()


def test_main_catalogue_absent_message_clair(tmp_path, monkeypatch, capsys):
    (tmp_path / "src" / "app").mkdir(parents=True)
    (tmp_path / "src" / "app" / "Accueil.py").write_text("", encoding="utf-8")
    (tmp_path / ".streamlit").mkdir()
    (tmp_path / ".streamlit" / "config.toml").write_text("", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(launcher, "ROOT", tmp_path)

    assert launcher.main([]) == 1
    assert "Impossible de créer data/models.json" in capsys.readouterr().err


def test_main_lance_streamlit_depuis_la_racine(monkeypatch, tmp_path):
    from streamlit.web import cli as stcli

    seen = {}
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(launcher, "ensure_models_json", lambda root: False)
    monkeypatch.setattr(stcli, "main", lambda: seen.update(argv=list(launcher.sys.argv)))
    monkeypatch.setattr(launcher.sys, "argv", ["wavelocalai"])

    assert launcher.main(["--server.port", "8600"]) == 0
    assert seen["argv"][:2] == ["streamlit", "run"]
    assert seen["argv"][2].endswith("Accueil.py")
    assert seen["argv"][3:] == ["--server.port", "8600"]
    assert launcher.os.getcwd() == str(launcher.ROOT)
