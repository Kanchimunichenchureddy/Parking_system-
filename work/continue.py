from pathlib import Path
p=Path('outputs/parkreceipt/frontend/src/main.tsx');s=p.read_text()
s=s.replace("import './style.css';","import './style.css';\nimport {readPending,savePending,clearPending,type Draft} from './recovery';")
s=s.replace("async function api<T>","class ApiError extends Error { constructor(message:string,public status:number){super(message)} }\nasync function api<T>")
s=s.replace("throw Error(typeof e.detail==='string'?e.detail:'Please check the fields and try again.');","throw new ApiError(typeof e.detail==='string'?e.detail:'Please check the fields and try again.',r.status);")
s=s.replace("[key,setKey]=useState(crypto.randomUUID()),[method,setMethod]=useState('cash');","[saved,setSaved]=useState<Draft|null>(()=>readPending(slug)),[method,setMethod]=useState(()=>readPending(slug)?.method||'cash');")
a=s.index('<form className="card" onChange=');b=s.index('><div className="eyebrow">YOU ARE PARKING AT',a)
s=s[:a]+'''<form className="card" onSubmit={async e=>{
 e.preventDefault();if(!loc||busy)return;setBusy(true);setErr('');
 const f=new FormData(e.currentTarget);
 const draft=saved||{location_slug:slug,vehicle:String(f.get('vehicle')),phone:String(f.get('phone')||'')||null,method,idempotency_key:crypto.randomUUID()};
 try{
  savePending(draft);setSaved(draft);
  const r=await api<Row>('/requests','POST',draft);
  go('/request/'+r.token);clearPending(slug);
 }catch(e){
  if(e instanceof ApiError&&[400,404,422].includes(e.status)){clearPending(slug);setSaved(null)}
  setErr((e as Error).message);
 }finally{setBusy(false)}
}}''' + s[b:]
s=s.replace('<label>Vehicle registration<input name="vehicle"','{saved&&<p className="note" role="status">A request is awaiting a server response. Retry it below to recover the same request safely.</p>}<label>Vehicle registration<input readOnly={!!saved||busy} defaultValue={saved?.vehicle} name="vehicle"')
s=s.replace('<input type="tel" name="phone"','<input readOnly={!!saved||busy} defaultValue={saved?.phone||\'\'} type="tel" name="phone"')
s=s.replace('<fieldset disabled={busy}>','<fieldset disabled={busy||!!saved}>')
s=s.replace("{busy?'Creating request…':method==='cash'", "{busy?'Checking request…':saved?'Retry saved request →':method==='cash'")
s=s.replace("[notice,setNotice]=useState('');const query=", "[notice,setNotice]=useState(''),[applied,setApplied]=useState('');const query=")
a=s.index('async function load(){setBusy(true);try{setReport');b=s.index('useEffect(()=>{api<typeof staff>',a)
s=s[:a]+'''async function load(filters=applied||query,nextPage=page){setBusy(true);try{const result=await api<Report>('/owner/report?'+filters+'&page='+nextPage);setReport(result);setApplied(filters);setPage(nextPage);setErr('')}catch(e){setErr((e as Error).message)}finally{setBusy(false)}}useEffect(()=>{load(query,1)},[]);'''+s[b:]
a=s.index('async function qr(l:Loc)');b=s.index('return <><div className="heading">',a)
s=s[:a]+'''async function qr(l:Loc){try{
 const target=location.origin+'/p/'+l.slug;
 const code=await QRCode.toDataURL(target,{width:840,margin:4,errorCorrectionLevel:'M'});
 const image=new Image();image.src=code;await image.decode();
 const canvas=document.createElement('canvas');canvas.width=1200;canvas.height=1600;
 const ctx=canvas.getContext('2d');if(!ctx)throw Error('Cannot create sign in this browser.');
 ctx.fillStyle='#ffffff';ctx.fillRect(0,0,1200,1600);ctx.textAlign='center';
 ctx.fillStyle='#203d35';ctx.font='bold 38px sans-serif';ctx.fillText('ParkReceipt · RESEARCH PROTOTYPE',600,110,1100);
 ctx.font='bold 78px sans-serif';ctx.fillText(l.name,600,240,1100);
 ctx.font='44px sans-serif';ctx.fillText('Scan to request your parking receipt',600,330,1100);
 ctx.drawImage(image,180,390,840,840);
 ctx.font='32px sans-serif';ctx.fillText('Check the current fee before submitting.',600,1270,1100);
 ctx.fillText('Pay cash to the attendant for confirmation.',600,1330,1100);
 ctx.font='bold 30px sans-serif';ctx.fillText('Online payment is a demo — no money collected.',600,1400,1100);
 ctx.font='24px sans-serif';ctx.fillText(target,600,1490,1100);
 const a=document.createElement('a');a.href=canvas.toDataURL('image/png');a.download=l.slug+'-sign.png';a.click();
 setNotice('Location sign downloaded. Test the QR on a phone before printing.');
 }catch(e){setErr((e as Error).message)}}'''+s[b:]
s=s.replace("<a className=\"button secondary\" href={'/api/owner/export?'+query}>Download CSV ↓</a>","{applied&&<a className=\"button secondary\" href={'/api/owner/export?'+applied}>Download displayed CSV ↓</a>}")
s=s.replace("if(page!==1)setPage(1);else load()","load(query,1)")
s=s.replace('disabled={page===1} onClick={()=>setPage(page-1)}','disabled={busy||page===1} onClick={()=>load(applied,page-1)}')
s=s.replace('disabled={page*25>=report.total} onClick={()=>setPage(page+1)}','disabled={busy||page*25>=report.total} onClick={()=>load(applied,page+1)}')
s=s.replace('Download QR code ↓','Download printable sign ↓')
s=s.replace('Print with the location name and “Scan to pay / Research prototype”.','Signs include the location name, instructions, and a clear demo label. Scan each sign on a phone before printing.')
p.write_text(s)
