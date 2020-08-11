import os
import re


# conf
PROJECT = 'assertpy'
SRC_DIR = os.path.join(os.getcwd(), 'build')
SRC = os.path.join(SRC_DIR, 'assertpy.html')
OUT_DIR = os.path.join(os.getcwd(), 'out')
OUT = os.path.join(OUT_DIR, 'docs.html')


def load(filename):
    with open(filename, 'r') as fp:
        return fp.read()


def save(target, contents):
    with open(target, 'w') as fp:
        fp.write(contents)


if __name__ == '__main__':
    print('\nFIXUP')
    print(f'  src={SRC}')
    print(f'  out={OUT}')

    if not os.path.exists(OUT_DIR):
        os.makedirs(OUT_DIR)

    if not os.path.isfile(SRC):
        print(f'bad src filename {SRC}')

    html = load(SRC)
    html = html.replace('<h1>', '<h1 class="title">')

    html = html.replace('"admonition-title">Tip</p>\n<p>', '"message-header">Tip</p>\n<p class="message-body">')
    html = html.replace('"admonition-title">Note</p>\n<p>', '"message-header">Note</p>\n<p class="message-body">')
    html = html.replace('"admonition-title">See also</p>\n<p>', '"message-header">See Also</p>\n<p class="message-body">')
    html = html.replace('"admonition tip"', '"message is-primary"')
    html = html.replace('"admonition note"', '"message is-info"')
    html = html.replace('"admonition seealso"', '"message is-link"')

    html = html.replace('<div class="highlight-default notranslate"><div class="highlight"><pre><span></span>', '<pre class="code"><code class="python">')
    html = html.replace('</pre></div>\n</div>', '</code></pre>')

    html = html.replace('class="code"><code class="python"><span class="mi">2019',
                        'class="code"><code class="bash"><span class="mi">2019')
    html = html.replace('class="code"><code class="python"><span class="ne">AssertionError</span><span class="p">:',
                        'class="code"><code class="bash"><span class="ne">AssertionError</span><span class="p">:')
    html = html.replace('class="code"><code class="python">AssertionError: soft assertion failures',
                        'class="code"><code class="bash">AssertionError: soft assertion failures')

    html = html.replace('<div class="section"', '<div class="section content"')
    html = html.replace('<p>Usage:</p>', '')
    html = html.replace('BR', '<br />')

    margin = 'style="margin:0.2em 0;"'
    html = html.replace('<dt class="field-odd">Parameters</dt>', f'<dt class="field-odd subtitle"{margin}>Parameters</dt>')
    html = html.replace('<dt class="field-even">Keyword Arguments</dt>', f'<dt class="field-even subtitle"{margin}>Keyword Arguments</dt>')
    html = html.replace('<p class="rubric">Examples</p>', f'<p class="rubric subtitle"{margin}>Examples</p>')
    html = html.replace('<dt class="field-odd">Returns</dt>', f'<dt class="field-odd subtitle"{margin}>Returns</dt>')
    html = html.replace('<dt class="field-even">Return type</dt>', f'<dt class="field-even subtitle"{margin}>Return type</dt>')
    html = html.replace('<dt class="field-odd">Raises</dt>', f'<dt class="field-odd subtitle"{margin}>Raises</dt>')

    html = html.replace('<dt id="assertpy.', '<dt class="title is-5" id="assertpy.')

    save(OUT, html)

    print('DONE!')
