// Run with: node --test tests/test_human_singularity_ui.cjs
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const source=fs.readFileSync(process.env.SCREENPLAY_TEST_APP||path.join(__dirname,'../src/screenplay_human/static/app.js'),'utf8');
const start=source.indexOf('function singularityControls(');
const end=source.indexOf('\nfunction renderSingularitySliders',start);
assert(start>=0&&end>start);
const controls=new Function(source.slice(start,end)+'; return singularityControls;')();

test('research sliders keep their row names, numeric limits and refreshed IDs; the final scrollbar is separate',()=>{
  const board=`Current panel: ResearchScreen.
  [u2_1] button: BACK
    [u2_2] row: Research Intrusion | 7; selected=False; progress=0.0%
      Research Intrusion
      7
      [u2_3] slider:  value=7, range=0..12
    [u2_4] row: Research Stealth | 0; selected=False; progress=0.0%
      Research Stealth
      0
      [u2_5] slider:  value=0, range=0..5
      [u2_6] slider:  value=0, range=0..0
      [u2_7] button: scroll up
      [u2_8] button: scroll down`;
  for(const revision of [2,3]){
    const parsed=controls(board.replaceAll('u2_',`u${revision}_`));
    const sliders=parsed.filter(c=>c.kind==='slider');
    assert.deepEqual(sliders.map(c=>[c.id,c.label,c.current,c.maximum]),[
      [`u${revision}_3`,'Research Intrusion',7,12],
      [`u${revision}_5`,'Research Stealth',0,5],
      [`u${revision}_6`,'列表滚动位置',0,0],
    ]);
    assert.equal(parsed.find(c=>c.id===`u${revision}_4`).sliderId,`u${revision}_5`);
    assert.equal(sliders[2].rowId,undefined);
  }
});

test('construction quantity slider stays distinct from its numeric text field and list scrollbar',()=>{
  const parsed=controls(`Current panel: MultipleBuildDialog.
    [u8_1] row: PC; selected=True
      [u8_2] slider:  value=0, range=0..0
      [u8_3] button: scroll up
      [u8_4] button: scroll down
  Number of items
  [u8_5] entry: 1
  [u8_6] slider:  value=1, range=0..8`);
  assert.deepEqual(parsed.filter(c=>c.kind==='slider').map(c=>[c.label,c.current,c.maximum]),[
    ['列表滚动位置',0,0],['Number of items · 数量',1,8],
  ]);
  assert.equal(parsed.find(c=>c.kind==='entry').id,'u8_5');
});
