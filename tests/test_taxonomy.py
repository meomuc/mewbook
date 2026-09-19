import json

from smartdoc.domain.taxonomy import Taxonomy, fold


def ids(categories):
    return [c.id for c in categories]


def test_fold_ignores_case_diacritics_and_punctuation():
    assert fold("Tuỳ bút") == fold("tùy-bút") == "tuy but"
    assert fold(None) == ""


def test_builtin_taxonomy_is_well_formed():
    taxonomy = Taxonomy.load_builtin()
    assert len(taxonomy) >= 40
    assert len(set(taxonomy.ids())) == len(taxonomy)
    assert all(category.name and category.group for category in taxonomy)
    assert "Văn học" in taxonomy.groups()
    assert taxonomy.fingerprint() == Taxonomy.load_builtin().fingerprint()


def test_labels_resolve_to_categories():
    taxonomy = Taxonomy.load_builtin()
    assert ids(taxonomy.match_labels("hồi ký, tuỳ bút")) == ["memoir_essay"]
    assert ids(taxonomy.resolve_labels(["unread", "lang:vi"])) == []


def test_firm_labels_beat_weak_ones():
    taxonomy = Taxonomy.load_builtin()
    assert ids(taxonomy.resolve_labels(["Fiction", "Mystery"])) == ["crime_mystery"]
    assert ids(taxonomy.resolve_labels(["Fiction"])) == ["novel"]


def test_only_firm_labels_count_as_already_categorised():
    taxonomy = Taxonomy.load_builtin()
    assert taxonomy.categories_in_tags("Fiction") == []
    assert ids(taxonomy.categories_in_tags("Cổ tích, AI")) == ["folktale", "ai_data"]
    assert taxonomy.without_category_tags("Cổ tích, đọc-sau, AI") == ["đọc-sau"]


def test_user_taxonomy_adds_overrides_and_disables(tmp_path):
    (tmp_path / "taxonomy.json").write_text(
        json.dumps(
            {
                "categories": [
                    {"id": "gardening", "name": "Làm vườn", "group": "Đời sống", "aliases": ["trồng cây cảnh"]},
                    {"id": "novel", "name": "Truyện dài"},
                    {"id": "horror", "disabled": True},
                ]
            }
        ),
        encoding="utf-8",
    )
    taxonomy = Taxonomy.load(tmp_path)
    assert taxonomy.get("gardening").name == "Làm vườn"
    assert taxonomy.get("novel").name == "Truyện dài"
    assert taxonomy.get("novel").aliases  # an override keeps what it did not mention
    assert "horror" not in taxonomy
    assert ids(taxonomy.match_labels("Trồng cây cảnh")) == ["gardening"]


def test_broken_user_taxonomy_is_ignored(tmp_path):
    (tmp_path / "taxonomy.json").write_text("{ not json", encoding="utf-8")
    assert len(Taxonomy.load(tmp_path)) == len(Taxonomy.load_builtin())
