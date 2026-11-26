import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';

const source = await readFile(new URL('../src/utils/secondaryPagination.ts', import.meta.url), 'utf8');
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2023, module: ts.ModuleKind.ESNext },
});
const { mergeUniquePage, getMessageNextPage, getWxUserPage } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`);

test('overlapping message pages retain order and replace the duplicate with its newest read state', () => {
  const first = [{ id: 1, unread: 1 }, { id: 2, unread: 1 }];
  const second = [{ id: 2, unread: 0 }, { id: 3, unread: 1 }, { id: 3, unread: 0 }];
  assert.deepEqual(mergeUniquePage(first, second, (item) => item.id), [
    { id: 1, unread: 1 }, { id: 2, unread: 0 }, { id: 3, unread: 0 },
  ]);
  assert.equal(first[1].unread, 1);
});

test('message cursors use server metadata and stop on the explicit last page', () => {
  assert.equal(getMessageNextPage({ has_more: true, next_page: 3 }, 1), 3);
  assert.equal(getMessageNextPage({ has_more: false, next_page: null }, 3), null);
});

test('missing message metadata and non-advancing cursors are errors instead of empty states', () => {
  for (const metadata of [{}, { has_more: true }, { has_more: true, next_page: null },
    { has_more: true, next_page: 1 }, { has_more: true, next_page: 0 },
    { has_more: true, next_page: 2.5 }, { has_more: true, next_page: Number.MAX_SAFE_INTEGER + 1 },
    { has_more: false }, { has_more: false, next_page: 2 }]) {
    assert.throws(() => getMessageNextPage(metadata, 1));
  }
});

test('WxPusher total boundaries distinguish empty, first page, and the 101st follower', () => {
  assert.deepEqual(getWxUserPage({ total: 0 }, 1, 100, 0), { total: 0, nextPage: null });
  assert.deepEqual(getWxUserPage({ total: 100 }, 1, 100, 100), { total: 100, nextPage: null });
  assert.deepEqual(getWxUserPage({ total: 101 }, 1, 100, 100), { total: 101, nextPage: 2 });
  assert.deepEqual(getWxUserPage({ total: 101 }, 2, 100, 1), { total: 101, nextPage: null });
});

test('WxPusher cursor uses requested pages even when follower pages overlap', () => {
  const first = Array.from({ length: 100 }, (_, index) => ({ uid: `UID_${index}` }));
  const second = Array.from({ length: 100 }, (_, index) => ({ uid: `UID_${index + 99}` }));
  const merged = mergeUniquePage(first, second, (user) => user.uid);
  assert.equal(merged.length, 199);
  assert.deepEqual(getWxUserPage({ total: 205 }, 2, 100, second.length), { total: 205, nextPage: 3 });
  assert.deepEqual(getWxUserPage({ total: 205 }, 3, 100, 5), { total: 205, nextPage: null });
});

test('WxPusher rejects missing totals and unexpectedly empty remaining pages', () => {
  for (const metadata of [{}, { total: -1 }, { total: 1.5 }, { total: Number.NaN }]) {
    assert.throws(() => getWxUserPage(metadata, 1, 100, 0));
  }
  assert.throws(() => getWxUserPage({ total: 101 }, 2, 100, 0));
  assert.throws(() => getWxUserPage({ total: 0 }, 1, 100, 1));
});
