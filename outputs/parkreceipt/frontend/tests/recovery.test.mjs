import {test,beforeEach} from 'node:test';
import assert from 'node:assert/strict';
import {readPending,savePending,clearPending} from '../src/recovery.ts';
let data;
beforeEach(()=>{data=new Map();Object.defineProperty(globalThis,'sessionStorage',{configurable:true,value:{getItem:k=>data.get(k)||null,setItem:(k,v)=>data.set(k,v),removeItem:k=>data.delete(k)}})});
const draft={location_slug:'parking-a',vehicle:'TEST01',phone:null,method:'cash',idempotency_key:'unchanged-key-for-safe-retry'};
test('refresh recovery keeps exact payload and retry key, isolated by location',()=>{
 savePending(draft);assert.deepEqual(readPending('parking-a'),draft);assert.equal(readPending('parking-b'),null);
 clearPending('parking-a');assert.equal(readPending('parking-a'),null);
});
test('storage denial blocks submission instead of losing the retry key',()=>{
 sessionStorage.setItem=()=>{throw Error('denied')};assert.throws(()=>savePending(draft),/No request was sent/);
});
test('corrupt stored drafts are ignored',()=>{
 data.set('parkreceipt:pending:parking-a','broken');assert.equal(readPending('parking-a'),null);
 data.set('parkreceipt:pending:parking-a',JSON.stringify({...draft,location_slug:'parking-b'}));assert.equal(readPending('parking-a'),null);
});

test('staff and customer recovery remain separate on a shared phone',()=>{
 savePending(draft);savePending({...draft,vehicle:'STAFF01'},'staff');
 assert.equal(readPending('parking-a').vehicle,'TEST01');
 assert.equal(readPending('parking-a','staff').vehicle,'STAFF01');
 clearPending('parking-a','staff');assert.equal(readPending('parking-a').vehicle,'TEST01');
});
