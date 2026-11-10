/* Angela López Mendoza · XAIHT — deterministic table semantics. */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const table = require('../../src/Tlachihuani.Jobs/wwwroot/table.js');
const job = (job_id, overrides={}) => ({job_id,name:job_id,selected_bytes:100,verified_bytes:50,phase:'downloading',
  seeds:1,peers:2,download_rate_bps:0,upload_rate_bps:0,eta_seconds:null,ratio:null,availability:null,
  queue_position:0,completed_at:null,tags:[],tracker_hosts:[],...overrides});
const order = (rows,key,direction=1) => table.sorted(rows,[{key,direction}]).map(x=>x.job_id);

test('completed stopped transfers are not restartable downloads',()=>{
  const done=job('done',{phase:'stopped',desired_state:'stopped',completed_at:123,delivery_state:'saved'});
  assert.equal(table.status(done),'completed');assert.equal(table.canAction(done,'start'),false);
  assert.equal(table.canAction(done,'recheck'),true);assert.equal(table.canAction(done,'reseed'),true);
  assert.equal(table.canAction(done,'cancel'),false);
});
test('recovery actions follow desired state and never confuse failures with stopped',()=>{
  for(const [phase,desired,action] of [['stopped','stopped','start'],['paused','paused','resume'],['failed','running','recheck']]) {
    const row=job(phase,{phase,desired_state:desired});assert.equal(table.canAction(row,action),true);
    if(phase==='failed')assert.equal(table.canAction(row,'start'),false);
  }
  assert.equal(table.canAction(job('cancelled',{desired_state:'cancelled'}),'recheck'),false);
  assert.equal(table.canAction(job('checking',{phase:'checking'}),'recheck'),false);
});
test('stalled automatic retry is visible without claiming a failed download',()=>{
  assert.equal(table.status(job('retry',{phase:'queued',queue_reason:'stalled_retry'})),'queued · retry scheduled');
});

test('exactly twelve data columns; Select is never sortable',()=>{
  assert.equal(table.columns.length,12);assert.equal(new Set(table.columns.map(x=>x.key)).size,12);
  assert.ok(!table.columns.some(x=>/select$/i.test(x.key)));
});
for(const key of ['selected_bytes','download_rate_bps','upload_rate_bps','eta_seconds','ratio','availability','queue_position','completed_at']) {
  for(const direction of [1,-1]) test(`${key} orders numbers and leaves unknowns last (${direction})`,()=>{
    const rows=[job('null',{[key]:null}),job('ten',{[key]:10}),job('two',{[key]:2}),job('nan',{[key]:NaN})];
    const result=order(rows,key,direction);
    assert.deepEqual(result.slice(0,2),direction===1?['two','ten']:['ten','two']);
    assert.deepEqual(new Set(result.slice(2)),new Set(['null','nan']));
  });
}
test('natural names, case-insensitive and stable by identity',()=>{
  const rows=[job('b',{name:'Book 2'}),job('c',{name:'Book 10'}),job('a',{name:'book 2'})];
  assert.deepEqual(order(rows,'name'),['a','b','c']);assert.deepEqual(order(rows,'name',-1),['c','a','b']);
});
test('progress uses percentage, not bytes or rounded text',()=>{
  const rows=[job('large',{selected_bytes:1000,verified_bytes:50}),job('small',{selected_bytes:10,verified_bytes:9}),job('empty',{selected_bytes:0})];
  assert.deepEqual(order(rows,'progress'),['empty','large','small']);
  assert.equal(table.progress(job('over',{verified_bytes:120})),100);
});
test('seed sorting uses peers as a secondary numeric key',()=>{
  const rows=[job('more-peers',{seeds:2,peers:12}),job('more-seeds',{seeds:10,peers:0}),job('less-peers',{seeds:2,peers:3})];
  assert.deepEqual(order(rows,'seeds'),['less-peers','more-peers','more-seeds']);
  assert.deepEqual(order(rows,'seeds',-1),['more-seeds','more-peers','less-peers']);
});
test('status sorting matches the displayed delivery state',()=>{
  const rows=[job('saving',{phase:'completed',completed_at:100,delivery_state:'pending'}),job('done',{phase:'completed',completed_at:101,delivery_state:'saved'}),job('active')];
  assert.deepEqual(order(rows,'phase'),['done','active','saving']);
  assert.equal(table.status(job('failed',{completed_at:100,delivery_state:'failed'})),'Download verified · saving failed');
});
test('negative ETA and absent completion stay unknown; zero ETA is known',()=>{
  assert.deepEqual(order([job('unknown',{eta_seconds:-1}),job('done',{eta_seconds:0})],'eta_seconds',-1),['done','unknown']);
  assert.deepEqual(order([job('unknown',{completed_at:0}),job('done',{completed_at:1})],'completed_at',-1),['done','unknown']);
});
test('multi-sort prioritizes each key without mutating the queue',()=>{
  const rows=[job('b',{name:'B',seeds:3}),job('a',{name:'A',seeds:3}),job('c',{name:'C',seeds:2})];
  assert.deepEqual(table.sorted(rows,[{key:'seeds',direction:-1},{key:'name',direction:1}]).map(x=>x.job_id),['a','b','c']);
  assert.deepEqual(rows.map(x=>x.job_id),['b','a','c']);
});
test('untrusted sort preferences discard invalid and duplicate fields',()=>{
  assert.deepEqual(table.normalizeSorts([{key:'__proto__'},{key:'name',direction:-1},{key:'name'}]),[{key:'name',direction:-1}]);
  assert.deepEqual(table.normalizeSorts('wrong'),[{key:'name',direction:1}]);
});
test('search combines accent-insensitive terms across metadata and paths',()=>{
  const row=job('id',{name:'Álgebra 2',category:'Books',tags:['Math'],tracker_hosts:['tracker.example'],saved_to:'C:/Downloads/Texts'});
  assert.ok(table.matches(row,{search:'ALGEBRA math downloads tracker.example'}));
  assert.ok(!table.matches(row,{search:'algebra missing'}));
});
test('filters compose and progress bounds are inclusive',()=>{
  const row=job('x',{category:'Books',tags:['Math'],tracker_hosts:['local'],download_rate_bps:5,desired_state:'running'});
  assert.ok(table.matches(row,{category:'Books',tag:'Math',tracker:'local',activity:'active',minProgress:'50',maxProgress:'50'}));
  for(const filters of [{category:'Video'},{tag:'Other'},{tracker:'remote'},{activity:'idle'},{minProgress:'51'},{maxProgress:'49'}])assert.ok(!table.matches(row,filters));
});
test('pagination never drops final rows and clamps shrinking queues',()=>{
  const rows=Array.from({length:263},(_,i)=>job(String(i)));
  assert.equal(table.paginate(rows,6,50).rows.length,13);
  assert.equal(table.paginate(rows,99,50).page,6);
  assert.equal(table.paginate(rows,1,0).rows.length,263);
  assert.deepEqual(table.paginate([],4,25),{rows:[],page:1,pages:1,first:0,last:0});
});
