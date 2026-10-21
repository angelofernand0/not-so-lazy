from notsolazy.clean import clean_html, normalize_text


def test_hidden_xbrl_wrappers_and_comments_preserve_visible_text() -> None:
    payload = (
        b"""<html><body><ix:header>Hidden taxonomy</ix:header><p>ri"""
        b"""<!-- note -->sk <ix:nonNumeric>evidence</ix:nonNumeric> remains.</p>"""
        b"""<div style="display: none">Invisible facts</div><p>After """
        b"""<span style="visibility:hidden">secret</span> text.</p></body></html>"""
    )
    blocks = clean_html(payload)
    assert [block.text for block in blocks] == ["risk evidence remains.", "After text."]


def test_unicode_normalization_and_inline_css_features() -> None:
    payload = (
        "<p>"
        '<span style="font-weight:700;font-style:italic;text-decoration:underline">'
        "“ＲＩＳＫ” – costs&nbsp;rise."
        "</span></p><p><b>Only a word"
        "</b> in this long plain body paragraph is bold.</p>"
    ).encode()
    heading, body = clean_html(payload)
    assert heading.text == '"RISK" - costs rise.'
    assert heading.is_bold and heading.is_italic and heading.is_underlined
    assert not body.is_bold
    assert normalize_text("can\u00adnot  do\nthis") == "cannot do this"


def test_css_normal_overrides_bold_and_italic_ancestors() -> None:
    blocks = clean_html(
        b'<div style="font-weight:700;font-style:italic">'
        b'<p style="font-weight:400;font-style:normal">Plain paragraph.</p>'
        b"</div>"
    )
    assert not blocks[0].is_bold and not blocks[0].is_italic


def test_block_order_list_and_inline_spacing_without_duplicates() -> None:
    blocks = clean_html(
        b"<div>Intro<p>First <b>bold</b> paragraph.</p><ul><li>List <i>entry"
        b"</i>.</li></ul><p>Last<br/>line.</p></div>"
    )
    assert [block.text for block in blocks] == [
        "Intro",
        "First bold paragraph.",
        "List entry.",
        "Last",
        "line.",
    ]
    assert blocks[2].is_list_item
    assert [block.source_index for block in blocks] == sorted(
        block.source_index for block in blocks
    )


def test_page_numbers_and_repeated_footers_do_not_remove_prominent_title() -> None:
    payload = '<html><body><div style="font-size:20pt">RISK FACTORS</div>'
    for page in range(4):
        payload += (
            f"<p>Substantive risk evidence on page {page}.</p>"
            f'<div style="font-size:7pt">RISK FACTORS</div>'
            f'<div style="font-size:7pt">{page} Example Corporation</div><p>{page}'
            f'</p><div style="page-break-after:always"></div>'
        )
    blocks = clean_html((payload + "</body></html>").encode())
    assert [block.text for block in blocks].count("RISK FACTORS") == 1
    assert blocks[0].font_size == 20
    assert not any("Example Corporation" in block.text for block in blocks)
    assert sum("Substantive risk evidence" in block.text for block in blocks) == 4


def test_toc_table_removed_but_inline_cross_reference_kept() -> None:
    links = "".join(
        f'<tr><td><a href="#item{i}">Item {i} heading</a></td></tr>' for i in range(1, 7)
    )
    payload = (
        f'<html><body><table>{links}</table><p>See <a href="#risks">risk details'
        f"</a> for context.</p></body></html>"
    )
    assert [block.text for block in clean_html(payload.encode())] == [
        "See risk details for context."
    ]


def test_large_layout_table_with_navigation_is_not_deleted() -> None:
    links = "".join(f'<a href="#item{i}">Item {i} heading</a>' for i in range(1, 7))
    payload = f"<table><tr><td>{links}<p>{'meaningful narrative ' * 400}</p></td></tr></table>"
    assert any("meaningful narrative" in block.text for block in clean_html(payload.encode()))


def test_declared_legacy_encoding_and_utf8_without_meta_are_decoded() -> None:
    assert clean_html("<p>“Risk” — evidence.</p>".encode())[0].text == '"Risk" - evidence.'
    legacy = '<meta charset="windows-1252"><p>“Risk” — evidence.</p>'.encode("cp1252")
    assert clean_html(legacy)[0].text == '"Risk" - evidence.'
