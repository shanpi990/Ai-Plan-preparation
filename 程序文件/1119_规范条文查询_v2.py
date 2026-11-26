"""深基坑规范选择和条号查询。正文按需从条文页面读取。"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import date
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import urljoin
from urllib.request import urlopen


CONFIG = Path(__file__).resolve().parent.parent / '配置文件'
DATABASE = CONFIG / '1119_规范条文库_v2.sqlite3'
CATALOG = CONFIG / '1119_深基坑规范目录_v2.json'
HEADING = re.compile(r'^(\d+(?:\.\d+)?)\s*[^\d.\s]')
CLAUSE = re.compile(r'(?m)^\s*(\d{1,2}\.\d{1,2}\.\d{1,2})[ \t\u3000\xa0]*(?=[^\d.\s])')


def read_html(url):
    from bs4 import BeautifulSoup

    with urlopen(url, timeout=15) as response:
        return BeautifulSoup(response.read().decode('utf-8-sig'), 'html.parser')


def read_section(url, section):
    page = read_html(url)
    body = page.select_one('#b_con')
    if body is None:
        raise ValueError(f'页面缺少正文区域 {url}')
    for node in body.select('.twsm, #explain, script, style'):
        node.decompose()
    for node in body.select('br'):
        node.replace_with('\n')
    for node in body.select('p, div, li, tr'):
        node.append('\n')

    text = body.get_text().strip()
    matches = list(CLAUSE.finditer(text))
    results = {}
    for index, match in enumerate(matches):
        number = match.group(1)
        chapter, subsection, _ = number.split('.')
        if section not in (chapter, f'{chapter}.{subsection}') or number in results:
            continue
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        content = '\n'.join(line.strip() for line in text[match.end():end].splitlines() if line.strip())
        if content:
            results[number] = content
    return results


def index_standard(standard):
    catalog_url = standard.get('catalog')
    if not catalog_url:
        return []
    catalog = read_html(catalog_url)
    sections = {}
    for link in catalog.select('ul.newsul a[href*="article-"]'):
        heading = link.get_text(' ', strip=True)
        match = HEADING.match(heading)
        if match and match[1].split('.')[0] in standard['chapters']:
            sections[match[1]] = (heading, urljoin(catalog_url, link['href']))
    if not sections:
        raise ValueError(f'目录未返回预设章节 {standard["code"]}')

    references = {}
    for section, (heading, url) in sections.items():
        for number in read_section(url, section):
            existing = references.get(number)
            if existing is None or '.' in section:
                references[number] = (standard['code'], number, section, heading, url)
    if not references:
        raise ValueError(f'未找到条号 {standard["code"]}')
    return list(references.values())


def build(database):
    with CATALOG.open(encoding='utf-8') as file:
        standards = json.load(file)
    with ThreadPoolExecutor(max_workers=4) as pool:
        groups = list(pool.map(index_standard, standards))

    with database.open('xb'):
        pass
    with closing(sqlite3.connect(database)) as connection:
        connection.executescript('''
            PRAGMA foreign_keys = ON;
            CREATE TABLE standard (
                code TEXT PRIMARY KEY, title TEXT NOT NULL, effective_date TEXT NOT NULL,
                scope TEXT NOT NULL, default_selected INTEGER NOT NULL, whole_standard_mandatory INTEGER NOT NULL,
                source TEXT NOT NULL, read_url TEXT NOT NULL, indexed_chapters TEXT NOT NULL
            );
            CREATE TABLE clause_reference (
                standard_code TEXT NOT NULL REFERENCES standard(code), number TEXT NOT NULL,
                section TEXT NOT NULL, heading TEXT NOT NULL, url TEXT NOT NULL,
                PRIMARY KEY (standard_code, number)
            );
        ''')
        for standard, references in zip(standards, groups):
            connection.execute('INSERT INTO standard VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)', (
                standard['code'], standard['title'], standard['date'], standard['scope'], standard['default'],
                standard['mandatory'], standard['source'], standard.get('catalog') or standard['read_url'],
                '、'.join(sorted({section.split('.')[0] for _, _, section, _, _ in references}, key=int)),
            ))
            connection.executemany('INSERT INTO clause_reference VALUES (?, ?, ?, ?, ?)', references)
        connection.commit()


def lookup(*, as_of, codes=(), clause=None, include_text=False, database=DATABASE):
    as_of = date.fromisoformat(as_of).isoformat()
    codes = {''.join(code.upper().split()) for code in codes}
    with closing(sqlite3.connect(f'{Path(database).resolve().as_uri()}?mode=ro', uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        selected = [dict(row) for row in connection.execute('''
            SELECT s.*, (SELECT COUNT(*) FROM clause_reference r WHERE r.standard_code = s.code) AS clause_count
            FROM standard s WHERE effective_date <= ? ORDER BY rowid
        ''', (as_of,)) if not codes or row['code'].replace(' ', '') in codes]
        references = []
        for standard in selected:
            if not codes and not clause:
                continue
            query = 'SELECT * FROM clause_reference WHERE standard_code = ?'
            arguments = [standard['code']]
            if clause:
                query += ' AND number = ?'
                arguments.append(clause)
            rows = [dict(row) for row in connection.execute(query, arguments)]
            references.extend(sorted(rows, key=lambda row: tuple(map(int, row['number'].split('.')))))

    if include_text:
        if not clause or not codes:
            raise ValueError('读取正文时需指定标准编号和条号。')
        for reference in references:
            try:
                section = read_section(reference['url'], reference['section'])
            except (OSError, ValueError) as error:
                reference.update(text=None, text_status='在线正文读取失败', text_error=str(error))
                continue
            reference['text'] = section.get(reference['number'])
            reference['text_status'] = '在线正文已读取' if reference['text'] else '原文页面待核'

    return {'database_version': Path(database).stem, 'as_of': as_of,
            'standards': selected, 'clause_references': references}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', action='store_true')
    parser.add_argument('--date', help='YYYY-MM-DD')
    parser.add_argument('--code', action='append', default=[], help='标准编号，可重复指定')
    parser.add_argument('--clause', help='精确条号')
    parser.add_argument('--text', action='store_true', help='在线读取所查条号正文')
    args = parser.parse_args()
    try:
        if args.build:
            build(DATABASE)
        else:
            if not args.date:
                parser.error('查询需提供 --date。')
            result = lookup(as_of=args.date, codes=args.code, clause=args.clause, include_text=args.text)
            print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError, sqlite3.Error) as error:
        parser.exit(1, f'{error}\n')


if __name__ == '__main__':
    main()
