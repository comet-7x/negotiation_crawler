"""Unit tests for wto_site pure logic — no network.

Ported from wto_fish_crawler/tests/test_urlrules.py; import paths adapted for
the negotiation_crawler package structure.

Run with:  python -m pytest tests/ -q
"""

from __future__ import annotations

from negotiation_crawler.crawlers.wto_site import classifier
from negotiation_crawler.crawlers.wto_site.storage import dedup
from negotiation_crawler.crawlers.wto_site.storage.models import Tier
from negotiation_crawler.crawlers.wto_site.fetch import _kind
from negotiation_crawler.crawlers.wto_site.fetch.urlrules import (
    decide_tier,
    is_english,
    is_excluded,
    is_record_only_doc,
    normalize_url,
    should_crawl,
)

# --------------------------------------------------------------------------- #
# normalize_url
# --------------------------------------------------------------------------- #


def test_normalize_drops_fragment_and_lowercases_host():
    u = "HTTPS://WWW.WTO.ORG/english/tratop_e/rulesneg_e/fish_e/fish_e.htm#top"
    assert normalize_url(u) == (
        "https://www.wto.org/english/tratop_e/rulesneg_e/fish_e/fish_e.htm"
    )


def test_normalize_strips_tracking_and_sorts_query():
    u = "https://www.wto.org/x_e.htm?b=2&utm_source=news&a=1"
    assert normalize_url(u) == "https://www.wto.org/x_e.htm?a=1&b=2"


def test_normalize_is_idempotent():
    u = "https://docs.wto.org/dol2fe/Pages/SS/directdoc.aspx?filename=q:/WT/MIN22/33.pdf&Open=True"
    assert normalize_url(normalize_url(u)) == normalize_url(u)


def test_normalize_keeps_docs_filename_param():
    u = "https://docs.wto.org/x/directdoc.aspx?Open=True&filename=q:/WT/MIN22/33.pdf"
    norm = normalize_url(u)
    from urllib.parse import unquote
    assert "filename=" in norm and "MIN22" in unquote(norm)
    assert decide_tier(norm) is Tier.T2_DOCS


# --------------------------------------------------------------------------- #
# is_english
# --------------------------------------------------------------------------- #


def test_english_suffix_accept():
    assert is_english("https://www.wto.org/a/fish_e.htm")
    assert is_english("https://www.wto.org/a/fish_factsheet_e.pdf")


def test_french_spanish_suffix_reject():
    assert not is_english("https://www.wto.org/a/fish_f.htm")
    assert not is_english("https://www.wto.org/a/fish_s.pdf")


def test_language_path_reject():
    assert not is_english("https://www.wto.org/french/tratop_f/fish_f/fish_f.htm")
    assert not is_english("https://www.wto.org/spanish/x_s.htm")


def test_language_neutral_allowed():
    assert is_english("https://docs.wto.org/x/directdoc.aspx?filename=q:/WT/L/1144.pdf")


# --------------------------------------------------------------------------- #
# decide_tier
# --------------------------------------------------------------------------- #


def test_tier1_fish_dir():
    assert decide_tier(
        "https://www.wto.org/english/tratop_e/rulesneg_e/fish_e/fish_e.htm"
    ) is Tier.T1_SITE


def test_tier1_legal_text_other_dir():
    assert decide_tier(
        "https://www.wto.org/english/docs_e/legal_e/fish_e.htm"
    ) is Tier.T1_SITE


def test_tier1_news_requires_fish_relevance():
    assert decide_tier(
        "https://www.wto.org/english/news_e/news25_e/fish_15sep25_e.htm"
    ) is Tier.T1_SITE
    assert decide_tier(
        "https://www.wto.org/english/news_e/news25_e/dgno_03jan25_e.htm"
    ) is not Tier.T1_SITE


def test_tier2_doc_series_whitelist():
    assert decide_tier(
        "https://docs.wto.org/x/directdoc.aspx?filename=q:/WT/MIN22/33.pdf&Open=True"
    ) is Tier.T2_DOCS
    assert decide_tier(
        "https://docs.wto.org/x/directdoc.aspx?filename=q:/TN/RL/W/100.pdf"
    ) is Tier.T2_DOCS


def test_tier2_rejects_unwhitelisted_series():
    assert decide_tier(
        "https://docs.wto.org/x/directdoc.aspx?filename=q:/G/AG/W/1.pdf"
    ) is not Tier.T2_DOCS


def test_tier3_external():
    assert decide_tier("https://www.fao.org/3/cc0461en/online/sofia.html") is Tier.T3_EXTERNAL
    assert decide_tier("https://www.oecd.org/fisheries/") is Tier.T3_EXTERNAL


def test_wto_unrelated_page_rejected():
    assert decide_tier(
        "https://www.wto.org/english/tratop_e/agric_e/agric_e.htm"
    ) is Tier.REJECT


# --------------------------------------------------------------------------- #
# should_crawl
# --------------------------------------------------------------------------- #


def test_should_crawl_gate():
    assert should_crawl("https://www.wto.org/english/tratop_e/rulesneg_e/fish_e/fish_e.htm")
    assert not should_crawl("https://www.wto.org/french/tratop_f/fish_f/fish_f.htm")
    assert not should_crawl("https://www.fao.org/x.html")


# --------------------------------------------------------------------------- #
# classify
# --------------------------------------------------------------------------- #


def test_classify_url_rules():
    assert classifier.classify("https://www.wto.org/english/docs_e/legal_e/fish_e.htm") == "legal_text"
    assert classifier.classify(
        "https://www.wto.org/english/tratop_e/rulesneg_e/fish_e/fish_acceptances_e.htm"
    ) == "ratification"
    assert classifier.classify(
        "https://www.wto.org/english/tratop_e/rulesneg_e/fish_e/fish_e.htm"
    ) == "overview"
    assert classifier.classify(
        "https://docs.wto.org/x?filename=q:/WT/MIN22/33.pdf"
    ) == "mandate_decision"
    assert classifier.classify(
        "https://docs.wto.org/x?filename=q:/TN/RL/W/1.pdf"
    ) == "negotiation_submission"


def test_classify_title_fallback():
    assert classifier.classify(
        "https://www.wto.org/english/foo_e.htm",
        "Committee on Fisheries Subsidies",
    ) == "committee"
    assert classifier.classify(
        "https://www.wto.org/english/foo_e.htm", "random title"
    ) == "uncategorized"


def test_classify_new_categories():
    base = "https://www.wto.org/english/tratop_e/rulesneg_e/fish_e/"
    assert classifier.classify(base + "stories_tanzania_e.htm") == "case_story"
    assert classifier.classify(base + "stories-malaysia_e.htm") == "case_story"
    assert classifier.classify(base + "fish_fund_e.htm") == "fish_fund"
    assert classifier.classify(base + "1982_unclos.pdf") == "international_instrument"
    assert classifier.classify(base + "2009_psma.pdf") == "international_instrument"
    assert classifier.classify(base + "ngr_presentation_on_rfmo_as.pdf") == "negotiation_submission"
    assert classifier.classify(
        base + "agreement_on_fisheries_subsidies_information_session_22_may_2025_final.pdf"
    ) == "publication"


def test_minist_briefing_gated_in_scope():
    assert decide_tier(
        "https://www.wto.org/english/thewto_e/minist_e/mc13_e/briefing_notes_e/fisheries_subsidies_e.htm"
    ) is Tier.T1_SITE
    assert decide_tier(
        "https://www.wto.org/english/thewto_e/minist_e/mc13_e/briefing_notes_e/agriculture_e.htm"
    ) is not Tier.T1_SITE


def test_news22_in_scope():
    assert decide_tier(
        "https://www.wto.org/english/news_e/news22_e/fish_08nov22_e.htm"
    ) is Tier.T1_SITE


def test_minist_classified():
    assert classifier.classify(
        "https://www.wto.org/english/thewto_e/minist_e/mc13_e/briefing_notes_e/fisheries_subsidies_e.htm"
    ) == "ministerial"
    iframe = "https://www.wto.org/english/tratop_e/rulesneg_e/fish_e/fish_map_iframe_e.htm"
    assert is_excluded(iframe)
    assert not should_crawl(iframe)
    err = "https://www.wto.org/error/error_404.htm"
    assert is_excluded(err)
    assert not should_crawl(err)


# --------------------------------------------------------------------------- #
# dedup
# --------------------------------------------------------------------------- #


def test_content_hash_whitespace_insensitive():
    assert dedup.hash_text("a   b\n c") == dedup.hash_text("a b c")


def test_dedup_tracker():
    d = dedup.Dedup()
    assert d.check_content("urlA", "hash1") is None
    assert d.check_content("urlB", "hash1") == "urlA"
    assert len(d.report) == 1
    assert d.check_content("urlC", "hash2") is None


def test_dedup_url_tracking():
    d = dedup.Dedup()
    assert not d.seen_url("u1")
    d.mark_url("u1")
    assert d.seen_url("u1")


# --------------------------------------------------------------------------- #
# document detection
# --------------------------------------------------------------------------- #


def test_kind_pdf_html():
    assert _kind("application/pdf", "x/a.pdf") == "pdf"
    assert _kind("text/html", "x/a.htm") == "html"


def test_kind_non_pdf_documents_by_extension():
    assert _kind("", "x/notify_e.docx") == "doc"
    assert _kind("", "x/data_e.xlsx") == "doc"
    assert _kind("", "x/slides_e.pptx") == "doc"


def test_kind_document_by_content_type_no_extension():
    assert _kind(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "x/download.aspx?id=5",
    ) == "doc"
    assert _kind("application/octet-stream", "x/get?ref=9") == "doc"


def test_kind_query_string_ignored():
    assert _kind("", "x/a.docx?ver=2") == "doc"


def test_record_only_docs():
    assert is_record_only_doc("https://www.wto.org/x/archive_e.zip")
    assert not is_record_only_doc("https://www.wto.org/x/video_e.mp4")
    assert not is_record_only_doc("https://www.wto.org/x/report_e.pdf")
    assert not is_record_only_doc("https://www.wto.org/x/notify_e.docx")
