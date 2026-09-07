import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

async function main() {
    let response;
    let captured;
    const removed = [];
    const context = {
        exports: {}, process, Error,
        window: { location: { href: '' } },
        localStorage: { removeItem: (key) => removed.push(key) },
        fetch: async (url, options) => {
            captured = { url, options };
            return response;
        },
    };
    const source = readFileSync(new URL('../lib/api.ts', import.meta.url), 'utf8');
    vm.runInNewContext(ts.transpileModule(source, {
        compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
    }).outputText, context);
    const { chatApi, knowledgeApi, ApiError } = context.exports;
    const ask = () => chatApi.ask('hello');
    const signal = new AbortController().signal;
    const exportVideo = () => knowledgeApi.exportMarkdown('BV1', 'original', 'session', 'operation', signal);

    response = new Response(JSON.stringify({ answer: 'ok', sources: [] }));
    assert.equal((await ask()).answer, 'ok');
    response = new Response('# Video');
    assert.equal(await (await exportVideo()).text(), '# Video');
    assert.equal(captured.options.signal, signal);
    assert.equal(captured.options.headers['Content-Type'], 'application/json');

    for (const call of [ask, exportVideo]) {
        response = new Response(JSON.stringify({ detail: 'failed' }), { status: 400 });
        await assert.rejects(call, (error) => error instanceof ApiError && error.status === 400 && error.message === 'failed');
        response = new Response('upstream unavailable', { status: 502 });
        await assert.rejects(call, (error) => error.status === 502 && error.message === 'upstream unavailable');
        response = new Response('', { status: 401 });
        await assert.rejects(call, /会话已过期/);
        assert.equal(context.window.location.href, '/');
    }
    assert.deepEqual(removed, ['bili_session', 'bili_user', 'bili_session', 'bili_user']);
    console.log('API checks passed');
}
main().catch((error) => { console.error(error); process.exitCode = 1; });
