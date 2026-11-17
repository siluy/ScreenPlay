// Private Worker, invoked only by the Pages service binding. The VPC binding
// is restricted to the one study service; clients cannot choose a destination.
const staticPaths = new Set(['/', '/join', '/admin', '/developer', '/app.js', '/style.css']);
const getPaths = new Set(['/api/about', '/api/session', '/api/admin/catalog', '/api/admin/overview', '/api/admin/export.json', '/api/admin/export.csv', '/api/admin/results.csv', '/api/admin/summary.csv']);
const postPaths = new Set(['/api/login', '/api/logout', '/api/consent', '/api/attempts', '/api/pause', '/api/resume', '/api/withdraw', '/api/admin/invitations']);
const MAX_BODY = 65536;

function failure(request, status, code) {
  const api = new URL(request.url).pathname.startsWith('/api/');
  const body = api ? JSON.stringify({error: code}) : `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ScreenPlay · 等待研究主机</title><style>body{background:#f4f4ed;color:#172c31;font:18px/1.8 system-ui;margin:12vh auto;padding:24px;max-width:620px}a{color:#14635b}h1{font-size:32px}</style><h1>研究主机暂时未连接</h1><p>你的邀请链接仍可保留。请稍后刷新，或联系研究负责人。</p><p>已开始的任务按研究规则继续计时；网络故障不代表操作没有执行，请使用作答页的恢复连接功能确认结果。</p><a href="/">重新连接 →</a></html>`;
  return new Response(request.method === 'HEAD' ? null : body, {status, headers:{
    'Content-Type':api?'application/json; charset=utf-8':'text/html; charset=utf-8',
    'Cache-Control':'no-store', 'Retry-After':'5', 'X-Content-Type-Options':'nosniff',
    'Referrer-Policy':'no-referrer', 'X-Frame-Options':'DENY',
    'Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'"
  }});
}

async function boundedBody(request) {
  if (!request.body) return new Uint8Array();
  const reader = request.body.getReader();
  const chunks = [];
  let size = 0;
  while (true) {
    const {done, value} = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > MAX_BODY) { await reader.cancel(); throw new RangeError('body_too_large'); }
    chunks.push(value);
  }
  const body = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {body.set(chunk, offset); offset += chunk.byteLength;}
  return body;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const origin = env.PUBLIC_ORIGIN;
    if (url.origin !== origin || url.search) return failure(request, 403, 'origin_not_allowed');
    const method = request.method;
    const isRead = method === 'GET' || method === 'HEAD';
    const allowed = isRead ? staticPaths.has(url.pathname) || getPaths.has(url.pathname) || /^\/api\/attempts\/[a-f0-9]{32}\/history$/.test(url.pathname)
      : method === 'POST' && (postPaths.has(url.pathname) || /^\/api\/attempts\/[a-f0-9]{32}\/actions$/.test(url.pathname));
    if (!allowed) return failure(request, 404, 'not_found');
    if (method === 'POST' && url.pathname === '/api/attempts' && env.DRAIN_NEW_ATTEMPTS === '1') return failure(request, 503, 'maintenance');
    const requestOrigin = request.headers.get('Origin');
    if (requestOrigin && requestOrigin !== origin) return failure(request, 403, 'origin_not_allowed');
    if (!isRead && (request.headers.get('X-Study-Request') !== '1' || request.headers.get('Content-Type')?.split(';')[0] !== 'application/json')) return failure(request, 403, 'invalid_request_headers');
    if (Number(request.headers.get('Content-Length')) > MAX_BODY) return failure(request, 413, 'body_too_large');
    let body;
    try { body = isRead ? undefined : await boundedBody(request); }
    catch { return failure(request, 413, 'body_too_large'); }
    // Build a fresh allowlist of headers. No caller-supplied forwarding or
    // destination header can broaden the private service's scope.
    const headers = new Headers();
    for (const name of ['Cookie', 'Accept', 'Content-Type', 'X-Study-Request', 'Origin']) {
      const value = request.headers.get(name); if (value !== null) headers.set(name, value);
    }
    const client = request.headers.get('CF-Connecting-IP');
    if (client) headers.set('X-Screenplay-Client-IP', client);
    const target = new URL(url.pathname, origin);
    target.protocol = 'http:'; // The binding routes only to the Mac's loopback port.
    try {
      const response = await env.STUDY_SERVICE.fetch(target.toString(), {
        method:isRead?'GET':'POST', headers, body, redirect:'manual', signal:AbortSignal.timeout(75000)
      });
      if (response.status >= 300 && response.status < 400) return failure(request, 502, 'origin_unavailable');
      if (response.status >= 500 && !response.headers.get('Content-Type')?.includes('application/json')) return failure(request, 503, 'origin_unavailable');
      const responseHeaders = new Headers(response.headers);
      responseHeaders.set('Cache-Control', 'no-store');
      responseHeaders.set('Strict-Transport-Security', 'max-age=31536000');
      responseHeaders.delete('Access-Control-Allow-Origin');
      return new Response(method==='HEAD'?null:response.body, {status:response.status, headers:responseHeaders});
    } catch {
      // Never retry an uncertain POST. The participant's stable request_id is
      // the only permitted replay mechanism.
      console.error(JSON.stringify({event:'study_origin_unavailable', method, route:url.pathname.startsWith('/api/')?'api':'page'}));
      return failure(request, 503, 'origin_unavailable');
    }
  }
};
