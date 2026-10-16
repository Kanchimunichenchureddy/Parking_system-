// Only a pending submission lives in tab storage; payment status always comes from the server.
export type Draft={location_slug:string;vehicle:string;phone:string|null;method:string;idempotency_key:string};
const key=(slug:string,scope:string)=>'parkreceipt:pending:'+(scope==='customer'?'':scope+':')+slug;
export function readPending(slug:string,scope='customer'):Draft|null{
 try{
  const raw=sessionStorage.getItem(key(slug,scope));if(!raw)return null;
  const d=JSON.parse(raw);
  if(d.location_slug!==slug||typeof d.vehicle!=='string'||!['cash','demo'].includes(d.method)||typeof d.idempotency_key!=='string'||d.idempotency_key.length<20||(d.phone!==null&&typeof d.phone!=='string'))return null;
  return d;
 }catch{return null}
}
export function savePending(d:Draft,scope='customer'){
 try{sessionStorage.setItem(key(d.location_slug,scope),JSON.stringify(d))}
 catch{throw Error('Allow tab storage before submitting so this request can be recovered after a refresh. No request was sent.')}
}
export function clearPending(slug:string,scope='customer'){try{sessionStorage.removeItem(key(slug,scope))}catch{/* server record is unaffected */}}
