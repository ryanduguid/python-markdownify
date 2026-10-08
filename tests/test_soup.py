import pytest  # type: ignore[import-not-found]
from bs4 import BeautifulSoup
from markdownify import MarkdownConverter, LSTRIP, RSTRIP, STRIP, STRIP_ONE


@pytest.mark.parametrize('mode,expected', [
    (STRIP, 'Hello'),
    (LSTRIP, 'Hello\n\n'),
    (RSTRIP, '\n\n\nHello'),
    (None, '\n\n\nHello\n\n'),
])
def test_tag_strip_document(mode, expected):
    soup = BeautifulSoup('<html>\n<body><div><p>Hello</p></div></body></html>', 'html.parser')
    assert MarkdownConverter(strip_document=mode).convert_soup(soup.html) == expected


@pytest.mark.parametrize('tag', ['html', 'body', 'div', 'p'])
def test_tag_default_strip_document(tag):
    soup = BeautifulSoup('<html>\n<body><div><p>Hello</p></div></body></html>', 'html.parser')
    assert MarkdownConverter().convert_soup(soup.find(tag)) == 'Hello'


@pytest.mark.parametrize('options,expected', [
    ({'convert': ['p']}, '\n\nHello\n\n'),
    ({'strip': ['[document]']}, '\n\nHello\n\n'),
    ({'convert': []}, 'Hello'),
])
@pytest.mark.parametrize('mode', [STRIP, LSTRIP, RSTRIP, None, 'invalid'])
def test_excluded_document_policy(options, expected, mode):
    soup = BeautifulSoup('<p>Hello</p>', 'html.parser')
    converter = MarkdownConverter(strip_document=mode, **options)
    assert converter.convert_soup(soup.p) == expected
    assert converter.convert_soup(soup) == expected


@pytest.mark.parametrize('options', [
    {'strip': []}, {'strip': ['div']}, {'convert': ['p', '[document]']},
])
def test_document_policy_enabled_independently_of_root_converter(options):
    soup = BeautifulSoup('<div><p>Hello</p></div>', 'html.parser')
    assert MarkdownConverter(**options).convert_soup(soup.div) == 'Hello'


@pytest.mark.parametrize('mode', ['invalid', STRIP_ONE])
@pytest.mark.parametrize('html', ['<p></p>', '<p>Hello</p>'])
def test_invalid_tag_document_mode(html, mode):
    soup = BeautifulSoup(html, 'html.parser')
    with pytest.raises(ValueError, match='^Invalid value for strip_document: %s$' % mode):
        MarkdownConverter(strip_document=mode).convert_soup(soup.p)


@pytest.mark.parametrize('mode,expected', [
    (STRIP, ' \tA\r\n\nB\t '),
    (LSTRIP, ' \tA\r\n\nB\t \n\n'),
    (RSTRIP, '\n\n \tA\r\n\nB\t '),
    (None, '\n\n \tA\r\n\nB\t \n\n'),
])
def test_custom_root_preserves_significant_whitespace(mode, expected):
    soup = BeautifulSoup('<root><b>child</b></root>', 'html.parser')
    calls = []

    class Converter(MarkdownConverter):
        def convert_root(self, el, text, parent_tags):
            assert el is soup.root
            assert text == '**child**'
            assert parent_tags == set()
            calls.append(el)
            return '\n\n \tA\r\n\nB\t \n\n'

    assert Converter(strip_document=mode).convert_soup(soup.root) == expected
    assert len(calls) == 1


@pytest.mark.parametrize('mode', [STRIP, None, 'invalid'])
def test_replacing_document_callback_remains_document_only(mode):
    soup = BeautifulSoup('<p>Hello</p>', 'html.parser')
    calls = []

    class Converter(MarkdownConverter):
        def convert__document_(self, el, text, parent_tags):
            assert el is soup
            assert text == '\n\nHello\n\n'
            assert parent_tags == set()
            calls.append(el)
            return '\n\nDOCUMENT\n\n'

    converter = Converter(strip_document=mode)
    assert converter.convert_soup(soup) == '\n\nDOCUMENT\n\n'
    if mode == 'invalid':
        with pytest.raises(ValueError):
            converter.convert_soup(soup.p)
    else:
        expected = 'Hello' if mode == STRIP else '\n\nHello\n\n'
        assert converter.convert_soup(soup.p) == expected
    assert len(calls) == 1


def test_process_tag_override_preserves_document_output():
    soup = BeautifulSoup('<p>Hello</p>', 'html.parser')
    calls = []

    class Converter(MarkdownConverter):
        def process_tag(self, node, parent_tags=None):
            assert parent_tags == set()
            calls.append(node)
            return '\n\nCUSTOM\n\n'

    converter = Converter()
    assert converter.convert_soup(soup) == '\n\nCUSTOM\n\n'
    assert converter.convert_soup(soup.p) == 'CUSTOM'
    assert len(calls) == 2
    assert calls[0] is soup and calls[1] is soup.p
    soup.name = '[DOCUMENT]'
    assert converter.convert_soup(soup) == '\n\nCUSTOM\n\n'


@pytest.mark.parametrize('available', [True, False])
def test_document_lookup_cache_and_original_tag_dispatch(available):
    soup = BeautifulSoup('<p>Hello</p>', 'html.parser')
    resolved = []
    converted = []
    processed = []

    class Converter(MarkdownConverter):
        def get_conv_fn(self, name):
            resolved.append(name)
            if name == '[document]' and not available:
                return None
            return super().get_conv_fn(name)

        def convert_p(self, el, text, parent_tags):
            converted.append((el, set(parent_tags)))
            return super().convert_p(el, text, parent_tags)

        def process_element(self, node, parent_tags=None):
            processed.append(node)
            return super().process_element(node, parent_tags)

    converter = Converter()
    expected = 'Hello' if available else '\n\nHello\n\n'
    for root in (soup.p, soup.p, soup, soup.p):
        assert converter.convert_soup(root) == expected
    assert resolved.count('[document]') == 1
    assert resolved.count('p') == 1
    assert len(converted) == 4
    assert all(el is soup.p for el, _ in converted)
    assert [parents for _, parents in converted] == [set(), set(), {'[document]'}, set()]
    assert len(processed) == 5
    assert sum(node is soup.p for node in processed) == 1


@pytest.mark.parametrize('mode', [STRIP, LSTRIP, RSTRIP, None, 'invalid'])
def test_attached_tree_relationships_survive_conversion(mode):
    soup = BeautifulSoup('<section><i>before</i><p>Hello</p><b>after</b></section>', 'html.parser')
    serialised = str(soup)
    nodes = [soup] + list(soup.descendants)
    links = [(node.parent, node.previous_sibling, node.next_sibling,
              node.previous_element, node.next_element) for node in nodes]
    converter = MarkdownConverter(strip_document=mode)
    for _ in range(2):
        if mode == 'invalid':
            with pytest.raises(ValueError):
                converter.convert_soup(soup.p)
        else:
            converter.convert_soup(soup.p)
        current_nodes = [soup] + list(soup.descendants)
        assert len(current_nodes) == len(nodes)
        assert all(current is original for current, original in zip(current_nodes, nodes))
        for node, original in zip(nodes, links):
            current = (node.parent, node.previous_sibling, node.next_sibling,
                       node.previous_element, node.next_element)
            assert all(a is b for a, b in zip(current, original))
        assert str(soup) == serialised


@pytest.mark.parametrize('mode,prefix,suffix', [
    (STRIP, '', ''), (LSTRIP, '', '\n\n'),
    (RSTRIP, '\n\n', ''), (None, '\n\n', '\n\n'),
])
@pytest.mark.parametrize('pre_mode,code', [
    (STRIP, '```\n  Hello\n```'),
    (STRIP_ONE, '```\n  \n  Hello  \n  \n```'),
    (None, '```\n  \n  \n  Hello  \n  \n  \n```'),
])
@pytest.mark.parametrize('tag', ['section', 'pre'])
def test_pre_root_and_descendant_keep_code_whitespace(mode, prefix, suffix, pre_mode, code, tag):
    soup = BeautifulSoup('<section><pre>  \n  \n  Hello  \n  \n  </pre></section>', 'html.parser')
    callbacks = []

    def language(el):
        assert el is soup.pre
        callbacks.append(el)

    converter = MarkdownConverter(strip_document=mode, strip_pre=pre_mode, code_language_callback=language)
    assert converter.convert_soup(soup.find(tag)) == prefix + code + suffix
    assert len(callbacks) == 1


@pytest.mark.parametrize('mode,expected', [(STRIP, 'ALIAS'), (None, '\n\nALIAS\n\n')])
def test_document_method_alias_keeps_original_root_dispatch(mode, expected):
    soup = BeautifulSoup('<p>Hello</p>', 'html.parser')
    root = soup.p
    root.name = '_document_'
    calls = []

    class Converter(MarkdownConverter):
        def convert__document_(self, el, text, parent_tags):
            assert el is root
            assert text == 'Hello'
            assert parent_tags == set()
            calls.append(el)
            return '\n\nALIAS\n\n'

    assert Converter(strip_document=mode).convert_soup(root) == expected
    assert len(calls) == 1


@pytest.mark.parametrize('mode', [STRIP, None])
def test_tag_lookup_caches_document_unavailability_before_state_changes(mode):
    soup = BeautifulSoup('<p>Hello</p>', 'html.parser')
    resolved = []
    document_calls = []

    class Converter(MarkdownConverter):
        available = False

        def get_conv_fn(self, name):
            resolved.append((name, self.available))
            if name == '[document]' and not self.available:
                return None
            return super().get_conv_fn(name)

        def convert__document_(self, el, text, parent_tags):
            document_calls.append(el)
            return super().convert__document_(el, text, parent_tags)

    converter = Converter(strip_document=mode)
    assert converter.convert_soup(soup.p) == '\n\nHello\n\n'
    converter.available = True
    assert converter.convert_soup(soup) == '\n\nHello\n\n'
    assert resolved == [('p', False), ('[document]', False)]
    assert document_calls == []
