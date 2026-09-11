const CACHE='lehmann1938-20260911015735';
const SHELL=['./','./index.html'];
self.addEventListener('install',e=>{
  e.waitUntil(caches.open(CACHE).then(c=>c.addAll(SHELL)).then(()=>self.skipWaiting()));
});
self.addEventListener('activate',e=>{
  e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k.indexOf('lehmann1938-')===0&&k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim()));
});
const isShell=u=>u.pathname.endsWith('/')||u.pathname.endsWith('/index.html');
self.addEventListener('fetch',e=>{
  const u=new URL(e.request.url);
  if(u.origin!==self.location.origin||e.request.method!=='GET')return; // mapbox tiles/cdn pass through
  if(isShell(u)){
    e.respondWith(fetch(e.request).then(r=>{const c=r.clone();caches.open(CACHE).then(cc=>cc.put(e.request,c));return r;}).catch(()=>caches.match(e.request)));
    return;
  }
  e.respondWith(caches.match(e.request).then(hit=>{
    const net=fetch(e.request).then(r=>{
      if(r.ok){const c=r.clone();caches.open(CACHE).then(cc=>cc.put(e.request,c));}
      return r;
    }).catch(()=>hit);
    return hit||net;
  }));
});
