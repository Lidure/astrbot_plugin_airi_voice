from pathlib import Path


def test_keyword_management_has_dedicated_search_input():
    page = Path("pages/airi-voice/index.html").read_text(encoding="utf-8")

    assert 'id="keyword-search-input"' in page
    assert 'type="search"' in page
    assert "搜索主关键词或额外关键词" in page


def test_keyword_search_filters_primary_names_and_aliases_client_side():
    script = Path("pages/airi-voice/app.js").read_text(encoding="utf-8")

    assert 'keywordQuery: ""' in script
    assert 'keywordSearch: document.getElementById("keyword-search-input")' in script
    assert "function filteredKeywordItems()" in script
    assert "item.name" in script
    assert "item.aliases" in script
    assert ".toLocaleLowerCase()" in script
    assert "const visibleItems = filteredKeywordItems();" in script
    assert 'elements.keywordSearch.addEventListener("input"' in script
    assert "renderKeywords();" in script


def test_keyword_search_reports_visible_and_total_counts_and_empty_result():
    page = Path("pages/airi-voice/index.html").read_text(encoding="utf-8")
    script = Path("pages/airi-voice/app.js").read_text(encoding="utf-8")

    assert "没有找到匹配的关键词" in page
    assert "当前显示 ${visibleItems.length} / ${state.keywordItems.length} 个主关键词" in script
