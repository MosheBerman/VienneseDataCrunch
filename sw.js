const CACHE='lehmann1938-v3';
const SHELL=['./','./index.html','./app.js','./data/meta.json'];
self.addEventListener('install',e=>{
  e.waitUntil(caches.open(CACHE).then(c=>c.addAll(SHELL)).then(()=>self.skipWaiting()));
});
self.addEventListener('activate',e=>{
  e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim()));
});
self.addEventListener('fetch',e=>{
  const u=new URL(e.request.url);
  if(u.origin!==self.location.origin||e.request.method!=='GET')return; // mapbox tiles/cdn pass through
  e.respondWith(caches.match(e.request).then(hit=>{
    const net=fetch(e.request).then(r=>{
      if(r.ok){const c=r.clone();caches.open(CACHE).then(cc=>cc.put(e.request,c));}
      return r;
    }).catch(()=>hit);
    return hit||net;
  }));
});
