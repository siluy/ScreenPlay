import test from 'node:test';
import assert from 'node:assert/strict';
import gateway from './gateway.mjs';
const origin = 'https://study.example.org';
const request = (path, body, extra={}) => new Request(origin+path, body===undefined?extra:{method:'POST',body,headers:{'Content-Type':'application/json','X-Study-Request':'1','Origin':origin,...extra}});

test('POST bytes, cookie and idempotency ID survive; spoofed proxy headers do not', async () => {
  const body = JSON.stringify({request_id:'same-id',observation_id:0,action:{type:'wait'}});
  let calls=0;
  const env={PUBLIC_ORIGIN:origin,STUDY_SERVICE:{async fetch(url, init){
    calls++; assert.equal(url,'http://study.example.org/api/attempts/'+'a'.repeat(32)+'/actions');
    assert.equal(new TextDecoder().decode(init.body),body);
    assert.equal(init.headers.get('Cookie'),'screenplay_session=one');
    assert.equal(init.headers.get('X-Screenplay-Client-IP'),'203.0.113.5');
    assert.equal(init.headers.get('X-Forwarded-Host'),null);
    assert.equal(init.redirect,'manual');
    return new Response('{"ok":true}',{headers:{'Content-Type':'application/json','Set-Cookie':'screenplay_session=one; Secure; HttpOnly'}});
  }}};
  const r=await gateway.fetch(request('/api/attempts/'+'a'.repeat(32)+'/actions',body,{'Cookie':'screenplay_session=one','CF-Connecting-IP':'203.0.113.5','X-Screenplay-Client-IP':'fake','X-Forwarded-Host':'evil.invalid'}),env);
  assert.equal(calls,1);assert.match(r.headers.get('Set-Cookie'),/Secure/);assert.equal(r.headers.get('Cache-Control'),'no-store');
});
test('untrusted origins, private files and oversized bodies never reach the Mac', async()=>{
  const env={PUBLIC_ORIGIN:origin,STUDY_SERVICE:{fetch(){assert.fail('must not forward')}}};
  for(const [req,status] of [[request('/api/login','{}',{'Origin':'https://evil.invalid'}),403], [request('/.env'),404], [request('/api/login','x'.repeat(65537)),413], [new Request('https://evil.invalid/'),403]]) assert.equal((await gateway.fetch(req,env)).status,status);
});
test('uncertain action is returned as recoverable error and never retried',async()=>{
  let calls=0;
  const env={PUBLIC_ORIGIN:origin,STUDY_SERVICE:{fetch(){calls++;throw new Error('private details');}}};
  const response=await gateway.fetch(request('/api/attempts','{}'),env);
  assert.equal(calls,1);assert.equal(response.status,503);assert.deepEqual(await response.json(),{error:'origin_unavailable'});
  const page=await gateway.fetch(request('/'),env);assert.match(await page.text(),/研究主机暂时未连接/);
});
test('redirects cannot forward credentials to another host',async()=>{
  const response=await gateway.fetch(request('/api/session'),{PUBLIC_ORIGIN:origin,STUDY_SERVICE:{async fetch(){return new Response(null,{status:302,headers:{Location:'https://evil.invalid'}})}}});
  assert.equal(response.status,502);assert.equal(response.headers.get('Location'),null);
});
test('draining only blocks new task starts and lets active actions finish',async()=>{
  let calls=0;
  const env={PUBLIC_ORIGIN:origin,DRAIN_NEW_ATTEMPTS:'1',STUDY_SERVICE:{async fetch(){calls++;return new Response('{}',{headers:{'Content-Type':'application/json'}});}}};
  assert.equal((await gateway.fetch(request('/api/attempts','{}'),env)).status,503);
  assert.equal(calls,0);
  assert.equal((await gateway.fetch(request('/api/attempts/'+'a'.repeat(32)+'/actions','{}'),env)).status,200);
  assert.equal(calls,1);
});
