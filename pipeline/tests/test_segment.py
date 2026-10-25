from notsolazy.clean import clean_html
from notsolazy.config import section_rule
from notsolazy.segment import segment

RULE = section_rule("1A")


def parse(html):
    blocks = clean_html(html.encode())
    text = "\n\n".join(b.text for b in blocks)
    return text, segment(text, "source", RULE, blocks)


def test_groups_summary_preamble_and_nested_subheads_keep_original_offsets():
    text, factors = parse("""<p>Item 1A. Risk Factors</p><p>Introductory context.</p>
        <p><b>Summary of Risk Factors</b></p><ul><li>Supply disruption</li><li>Credit risk</li></ul>
        <p><u>BUSINESS RISKS</u></p>
        <p><span style="font-weight:700">Supply disruptions could harm our business.</span></p>
        <p>We rely on suppliers.</p><p><b><i>International suppliers</i></b></p>
        <p>They operate overseas.</p><p><i>Credit losses could increase significantly.</i></p>
        <p>Credit evidence.</p>""")
    assert [f.role for f in factors] == ["preamble", "summary", "risk", "risk"]
    risk = factors[2]
    assert risk.group == "BUSINESS RISKS"
    assert "International suppliers" in risk.body
    assert "They operate overseas." in risk.body
    assert all(text[f.start : f.end] == f.text for f in factors)
    assert all(f.text_hash and f.item == RULE.item for f in factors)


def test_unformatted_paragraph_fallback_does_not_invent_headings():
    text, factors = parse("<p>Item 1A. Risk Factors</p><p>First risk.</p><p>Second risk.</p>")
    assert len(factors) == 2
    assert all(f.segmentation == "paragraph" and not f.heading for f in factors)
    assert all(f.role == "risk" and text[f.start : f.end] == f.body for f in factors)


def test_primary_rendered_text_is_preserved_when_formatting_is_absent():
    blocks = clean_html(b"<p><b>One heading could harm us.</b></p><p>Body.</p>")
    selected = "Item 1A. Risk Factors\n\nDifferent primary-rendered paragraph."
    factors = segment(selected, "a", RULE, blocks)
    assert len(factors) == 1
    assert factors[0].text == "Different primary-rendered paragraph."
    assert factors[0].segmentation == "paragraph"


def test_inline_styled_heading_is_split_without_changing_source_text():
    text, factors = parse(
        "<p>Item 1A. Risk Factors</p><p><b>Cloud investment could harm us.</b> "
        "We invest heavily in new capacity.</p><p>More evidence.</p>"
    )
    assert len(factors) == 1
    assert factors[0].heading == "Cloud investment could harm us."
    assert factors[0].body == "We invest heavily in new capacity.\n\nMore evidence."
    assert text[factors[0].start : factors[0].end] == factors[0].text


def test_group_with_missing_heading_format_uses_each_paragraph():
    _, factors = parse(
        "<p>Item 1A. Risk Factors</p><p><b>First risk harms our business.</b></p>"
        "<p>Body.</p><p><u>OTHER RISKS</u></p><p>Unstyled risk one.</p>"
        "<p>Unstyled risk two.</p>"
    )
    assert [f.segmentation for f in factors] == ["heading", "paragraph", "paragraph"]
    assert all(f.role == "risk" for f in factors)


def test_unstyled_final_period_belongs_to_inline_heading():
    text, factors = parse(
        "<p>Item 1A. Risk Factors</p><p><b>Our reputation may be harmed</b>"
        ". We rely on customer trust.</p>"
    )
    assert factors[0].heading == "Our reputation may be harmed."
    assert factors[0].body == "We rely on customer trust."
    assert text[factors[0].start : factors[0].end] == factors[0].text


def test_styled_summary_bullets_are_context_not_separate_risks():
    _, factors = parse(
        "<p>Item 1A. Risk Factors</p><p>Summary of Risk Factors</p>"
        "<ul><li><b>Suppliers could harm our business.</b></li>"
        "<li><i>Credit could harm our business.</i></li></ul>"
        "<p><b>Suppliers could harm our business.</b></p><p>Full evidence.</p>"
    )
    assert [f.role for f in factors] == ["summary", "risk"]
    assert "Credit could harm" in factors[0].text
    assert factors[1].group == ""


def test_repeated_larger_regular_weight_headings_keep_complete_bodies_and_offsets():
    body = "Substantive evidence about our operations and suppliers. " * 12
    payload = (
        '<p style="font-size:18pt">Risk Factors</p>'
        '<p style="font-size:9pt">Introductory context.</p>'
        '<p style="font-size:12pt;font-weight:400;color:#0068b5">'
        "Supplier disruptions could harm our business.</p>"
        f'<p style="font-size:9pt">{body}</p>'
        '<p style="font-size:9pt">Evidence continues on the next page.</p>'
        '<p style="font-size:12pt;font-weight:400;color:#0068b5">'
        "Credit losses could harm our business.</p>"
        f'<p style="font-size:9pt">{body} Final credit evidence.</p>'
    )
    text, factors = parse(payload)
    assert [f.role for f in factors] == ["preamble", "risk", "risk"]
    risks = [f for f in factors if f.role == "risk"]
    assert all(f.segmentation == "heading" for f in risks)
    assert risks[0].heading == "Supplier disruptions could harm our business."
    assert "Evidence continues on the next page." in risks[0].body
    assert risks[1].body.endswith("Final credit evidence.")
    assert all(text[f.start : f.end] == f.text for f in factors)


def test_body_size_and_one_enlarged_sentence_do_not_invent_headings():
    body = "Substantive evidence about our operations and suppliers. " * 12
    _, factors = parse(
        f'<p style="font-size:9pt">{body}</p>'
        '<p style="font-size:12pt">An isolated enlarged sentence is insufficient.</p>'
        f'<p style="font-size:9pt">{body}</p>'
        '<p style="font-size:9pt">A normal sentence ends here.</p>'
    )
    assert all(not f.heading and f.segmentation == "paragraph" for f in factors)


def test_font_inference_uses_selected_section_and_does_not_promote_list_bullets():
    body = "Substantive evidence about our operations and suppliers. " * 12
    blocks = clean_html(
        (
            '<p style="font-size:12pt">A larger heading in another section.</p>'
            "<p>Item 1A. Risk Factors</p>"
            f'<p style="font-size:9pt">{body}</p>'
            '<p style="font-size:12pt">Only one enlarged sentence in this section.</p>'
            '<ul style="font-size:12pt"><li>Our suppliers could harm us.</li>'
            "<li>Our customers could harm us.</li></ul>"
            f'<p style="font-size:9pt">{body}</p>'
        ).encode()
    )
    selected = "\n\n".join(b.text for b in blocks[1:])
    factors = segment(selected, "a", RULE, blocks)
    assert all(not f.heading for f in factors)
