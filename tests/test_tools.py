"""ツールのテスト（LLMもAPIキーも使わない）。"""

import json

from app import tools


def test_glossary_ids_are_unique_and_related_links_exist():
    terms = tools.load_glossary()
    ids = [t["id"] for t in terms]
    assert len(ids) == len(set(ids))
    for t in terms:
        for r in t["related"]:
            assert r in ids, f"{t['id']} の related に存在しない id: {r}"


def test_search_finds_term_by_name_and_alias():
    for query in ["LoRA", "lora", "Low-Rank Adaptation"]:
        hits = json.loads(tools.search_glossary(query))
        assert hits[0]["term"] == "LoRA", query


def test_search_finds_course_specific_term():
    hits = json.loads(tools.search_glossary("lecNN-start"))
    assert hits[0]["term"] == "lecNN-start タグ"


def test_search_limits_number_of_results():
    hits = json.loads(tools.search_glossary("エージェント"))
    assert 1 <= len(hits) <= tools.MAX_RESULTS


def test_search_reports_not_found():
    assert "見つかりませんでした" in tools.search_glossary("存在しない用語xyz")


def test_lecture_summary():
    assert "エージェント" in tools.get_lecture_summary(3)
    assert "まだありません" in tools.get_lecture_summary(99)


def test_default_question_of_lecture1_is_answerable_from_glossary():
    """第1回の既定の質問（app.ask）は、第3回のエージェントが用語集で正しく答えられること。"""
    from app.ask import DEFAULT_QUESTION

    assert "3レベル" in DEFAULT_QUESTION
    hits = json.loads(tools.search_glossary("3レベル"))
    assert hits[0]["term"] == "宿題の3レベル"


def test_quiz_tree_returns_only_requested_pages_in_request_order():
    data = json.loads(tools.lookup_quizzes(2, [4, 2, 4, 5]))
    assert data["missing_numbers"] == [5]
    assert [(p["page_id"], p["quiz_number"], p["role"]) for p in data["results"]] == [
        ("lec02-main-p056", 4, "設問"), ("lec02-main-p057", 4, "解説"),
        ("lec02-main-p026", 2, "設問"), ("lec02-main-p027", 2, "解説"),
    ]
    assert all(p["content"] for p in data["results"])


def test_quiz_tree_does_not_take_a_quiz_from_another_lecture():
    assert json.loads(tools.lookup_quizzes(1, [2])) == {"results": [], "missing_numbers": [2]}
