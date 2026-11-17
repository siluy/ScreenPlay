"use strict";
const $ = id => document.getElementById(id);
const state = {session: null, active: null, busy: false, catalog: [], invitationPresets: [], serverOffset: 0, pending: null, pendingControl: null, revision: 0};
const labels = {slide:"滑动方块",rotate:"旋转格子",toggle_lock:"切换格子锁定",move_node:"移动节点",move_cards:"移动纸牌",undo:"撤销",redo:"重做",restart:"重置当前盘面",wait:"等待",finish:"结束本题",open_panel:"打开面板",close_panel:"返回港口概览",buy:"购买一吨",sell:"出售一吨",hire:"雇用一人",fire:"解雇一人",click:"点击控件",set_value:"调整滑条数值",type_text:"填写文本",select_order:"选择订单",click_tile:"点击地块",draw_road:"绘制道路段",pan_map:"移动地图视野",push:"推动小球",activate_item:"使用背包首项",rotate_inventory:"轮换背包"};
const fields = {row:"行（从1开始）",column:"列（从1开始）",direction:"旋转方向",node:"节点编号",x:"X 坐标",y:"Y 坐标",source:"来源位置",target:"目标位置",count:"牌张数",commodity:"商品",panel:"面板",duration_ms:"等待毫秒",control:"当前盘面中的控件",value:"数值",text:"填写内容",index:"订单编号（从1开始）",x1:"起点 X",y1:"起点 Y",x2:"终点 X",y2:"终点 Y",dx:"水平推动量（正数向右）",dy:"垂直推动量（正数向下）"};
const choices = {clockwise:"顺时针",counterclockwise:"逆时针",trading:"交易面板",hiring:"雇员面板",map:"地图",vehicle:"车辆",orders:"订单",road:"道路",start_stop:"启停车辆",send_to_depot:"返回车库",turn_around:"车辆掉头",go_to:"前往：随后点击车站",delete_order:"删除所选订单",toggle_full_load:"切换满载策略",skip_order:"跳至下一订单",build_x:"沿 X 方向建路",build_y:"沿 Y 方向建路",remove_x:"沿 X 方向拆路",remove_y:"沿 Y 方向拆路"};
const errors = {maintenance:"服务正在更新，请稍后再开始下一题。已有结果已保存。",attempt_paused:"当前题已暂离，请先继续作答。",participant_paused:"你已暂离，请先继续作答。",participation_state_changed:"状态已更新，请刷新后再操作。",desktop_locked:"研究主机已锁屏。请联系负责人解锁后继续，暂离计时仍保持暂停。",desktop_unavailable:"研究主机暂不可用，请联系负责人。",rejoin_consent_required:"请确认恢复参与后继续。",withdraw_confirmation_required:"请确认结束参与。",origin_unavailable:"研究主机暂时未连接。请稍后恢复连接，确认上一步的结果。",invalid_login:"邀请码或管理口令不正确。",login_required:"请重新登录；使用原邀请码即可返回。",forbidden:"此入口需要相应权限。",desktop_busy:"图片任务主机正在供另一位受试者使用，请稍后再开始。",text_capacity_busy:"文本任务正在排队，请稍后再开始。",environment_startup_error:"原生环境未能启动，本次未计分。请联系研究负责人检查主机后重试。",environment_error:"环境中断，本次未计分。",participant_code_exists:"这个受试者编号已经存在，请换一个编号。",invalid_participant_code:"编号只能包含字母、数字、下划线或连字符。",text_not_supported:"所选题目中有尚不支持文本的任务。",invalid_tasks:"请选择至少一道有效且不重复的题目。",invalid_assignment:"任务分配参数无效。",login_rate_limited:"登录尝试过于频繁，请一分钟后再试。",attempt_finished:"本题已结束，正在同步结果。",stale_observation:"盘面已更新，正在同步最新状态。",participant_withdrawn:"你已退出本次研究。",consent_required:"请先阅读并确认作答说明。",server_error:"服务暂时无法响应，请恢复连接或联系研究负责人。",action_id_payload_conflict:"操作确认发生冲突，请联系研究负责人。",action_pending:"上一步操作尚在确认中。"};
const reasons = {success:"已完成",agent_finished:"主动结束 · 目标未完成",decision_budget_exhausted:"决策预算已用完",wall_budget_exhausted:"作答时间已用完",environment_error:"环境中断 · 未计分",environment_startup_error:"启动失败 · 未计分",server_interrupted:"服务中断 · 未计分",worker_interrupted:"环境进程中断 · 未计分",participant_withdrew:"退出研究 · 未计分",task_integrity_violation:"未满足任务规则",game_lost:"游戏失败"};

function notice(text, error=false) { $("notice").textContent=text; $("notice").className=error?"error":""; $("notice").hidden=!text; }
function textNode(tag, text, cls) { const e=document.createElement(tag);e.textContent=text;if(cls)e.className=cls;return e; }
function show(view) { for(const id of ["join-view","participant-view","admin-login-view","admin-view","developer-view"]) $(id).hidden=id!==view; }
function setBusy(value) { state.busy=value;document.body.classList.toggle("busy",value);for(const e of document.querySelectorAll("#attempt-panel button,#attempt-panel select,#attempt-panel input,#start-button"))e.disabled=value||e.dataset.controlDisabled==="true"; }
function requestId(){return Array.from(crypto.getRandomValues(new Uint8Array(16)),x=>x.toString(16).padStart(2,"0")).join("");}
async function api(path, body) {
  const options={credentials:"same-origin",cache:"no-store",headers:{"X-Study-Request":"1"}};
  if(body!==undefined){options.method="POST";options.headers["Content-Type"]="application/json";options.body=JSON.stringify(body);}
  let response;
  try{response=await fetch(path,{...options,signal:AbortSignal.timeout(90000)});}catch{const e=new Error("网络连接暂时中断，请恢复连接确认结果。");e.code="connection_lost";throw e;}
  const data=await response.json();
  if(!response.ok){const e=new Error(errors[data.error]||"请求未完成，请稍后再试。");e.code=data.error;e.status=response.status;throw e;}return data;
}
function pendingSave(value){state.pending=value;try{if(value)sessionStorage.setItem("screenplay.pending",JSON.stringify(value));else sessionStorage.removeItem("screenplay.pending");}catch{}}
async function confirmAction(title, description){$("confirm-title").textContent=title;$("confirm-text").textContent=description;const d=$("confirm-dialog");d.returnValue="cancel";d.showModal();return new Promise(resolve=>d.addEventListener("close",()=>resolve(d.returnValue==="yes"),{once:true}));}
function outcome(row){if(!row.result)return row.status==="paused"?"已暂离":row.status==="active"?"作答中":"准备中";return reasons[row.result.stop_reason]||(row.result.success===true?"已完成":row.result.success===false?"目标未完成":"中断 · 未计分");}

async function refresh(){
  const revision=state.revision;const data=await api("/api/session");if(revision!==state.revision)return;state.session=data;$("logout").hidden=false;
  if(data.role==="admin"){if(location.pathname==="/developer"){show("developer-view");return;}show("admin-view");await loadAdmin();return;}
  if(location.pathname==="/developer"){show("developer-view");return;}
  renderSession(data);
}
function renderSession(data){
  state.revision++;
  state.serverOffset=data.server_time*1000-Date.now();state.session=data;show("participant-view");const p=data.participant;if(state.pendingControl&&state.pendingControl.participant!==p.id)controlSave(null);
  $("participant-label").textContent=(data.protocol.actor==="validation"?"验证模式 · ":"")+"受试者 "+p.alias+" · 同一版本 v"+data.version;
  $("participant-title").textContent=p.withdrawn?"已结束本次参与":p.paused?"已暂离，随时可以回来。":p.done?"谢谢你，所有任务已提交。":"专注于眼前的这一步。";
  $("progress-label").textContent=`已评分 ${p.completed} / ${p.total} 题`;$("progress").max=p.total;$("progress").value=p.completed;
  $("consent-panel").hidden=p.consented||p.withdrawn;$("between-panel").hidden=!p.consented||!!data.active;$("attempt-panel").hidden=!data.active;
  if(p.withdrawn){$("between-panel").hidden=false;$("between-title").textContent="你的选择已保存";$("between-text").textContent="已有记录已保留。如果你只是暂时离开，可以恢复参与，继续未完成的题目。";}
  else if(p.paused){$("between-title").textContent=data.paused_attempt?"当前题已暂停":"进度已保存";$("between-text").textContent=data.paused_attempt?`已用 ${data.paused_attempt.decisions} 步，剩余 ${Math.ceil(data.paused_attempt.remaining_seconds)} 秒。休息不计时；点击继续回到原盘面。主机重启会使尚未完成的盘面失效，已评分结果仍保留。`:"可以关闭页面，下次使用原邀请码返回。已完成题目不会重做。";}
  else if(p.done){$("between-title").textContent="你也可以成为开发者";$("between-text").textContent="本次作答结果已保存。接下来可以了解这套任务的实现，或向负责人反馈体验。";}
  else if(p.next_task){$("between-title").textContent=`第 ${p.next_task.index} 题 · ${p.next_task.game}`;$("between-text").textContent=`${p.next_task.condition==="gui"?"图片与键鼠":"文本与结构化动作"}界面 · 最多 ${p.next_task.max_decisions??data.protocol.max_decisions} 次决策 · ${Math.round(data.protocol.wall_seconds/60)} 分钟。点击开始后，计时从盘面就绪开始。`;}
  $("start-button").hidden=p.done;$("develop-after").hidden=!p.done;$("withdraw-between").hidden=p.done||p.withdrawn;$("end-participation-between").hidden=p.done||p.withdrawn;$("pause-between").hidden=p.done||p.withdrawn||p.paused;$("logout").textContent=p.done||p.withdrawn?"退出登录":"暂离并退出登录";
  const last=data.attempts.at(-1);$("latest-result").hidden=!last||!!data.active;$("latest-result").textContent=last?`上一记录：第 ${last.number} 题 · ${outcome(last)}`:"";
  if(p.withdrawn)$("start-button").textContent="恢复参与 →";else if(p.paused)$("start-button").textContent=data.paused_attempt?"继续本题 →":"返回作答 →";else if(last?.status==="interrupted")$("start-button").textContent="重新启动本题 →";else $("start-button").textContent="开始下一题 →";
  $("attempt-rows").replaceChildren(...data.attempts.map(a=>{const tr=document.createElement("tr");for(const x of [a.number,a.game,a.condition==="gui"?"图片":"文本",outcome(a)])tr.append(textNode("td",x));return tr;}));
  if(data.active)renderAttempt(data.active);else state.active=null;
}
function renderAttempt(attempt){
  state.revision++;
  const changed=state.active?.attempt_id!==attempt.attempt_id;const oldObs=state.active?.observation?.observation_id;state.active=attempt;const o=attempt.observation;
  $("attempt-panel").hidden=false;$("between-panel").hidden=true;$("condition-badge").textContent=attempt.condition==="gui"?"图片界面":"文本界面";$("game-name").textContent=o.game||"原生任务";
  $("instruction").textContent=o.instruction||"";$("rules").textContent=o.rules||"";$("time-contract").textContent=o.time_contract?"思考时游戏模拟冻结；点击、键盘和等待按任务规则推进模拟。":"每次有效、无效或撤销动作都会按规则消耗决策预算。";
  if(o.simulation_updates_remaining!==undefined)$("time-contract").textContent+=` 剩余模拟推进机会：${o.simulation_updates_remaining}。`;
  const remaining=typeof o.budget_remaining==="object"?o.budget_remaining.decisions:o.budget_remaining;$("decisions").textContent=`剩余 ${remaining??0} 次决策`;
  $("gui-controls").hidden=attempt.condition!=="gui";$("text-controls").hidden=attempt.condition!=="text";
  if(changed||oldObs!==o.observation_id){
    if(o.image){$("game-image").src="data:image/png;base64,"+o.image.base64;$("game-image").width=o.image.width;$("game-image").height=o.image.height;}
    if(o.board_text!==undefined)$("board").textContent=o.board_text;
    renderSingularitySliders();
  }
  if(changed&&attempt.condition==="text"){
    const select=$("action-type");select.replaceChildren();for(const s of attempt.schemas){const n=s.function.name;if(n!=="finish"){const option=textNode("option",labels[n]||n);option.value=n;select.append(option);}}renderFields();
  }else if(attempt.condition==="text"&&oldObs!==o.observation_id&&o.interface_profile==="singularity-native-visible-widgets-v0"){
    renderFields();
  }
  $("receipt").textContent=o.receipt?.status==="rejected"?"上一步未被执行，但已按规则消耗一次决策，请检查动作参数。":o.receipt?.status==="executed"?"上一步已执行。请查看新的盘面。":"盘面已就绪，可以开始操作。";
  $("connection").textContent=state.pending?"等待确认":"已连接";updateClock();
}
// Derive labels only from the visible native text; slider IDs and bounds stay unchanged.
function singularityControls(board){
  const lines=board.split("\n"),controls=[];
  for(const [lineIndex,line] of lines.entries()){
    const match=line.match(/^(\s*)\[(u\d+_\d+)\] (button|row|slider|entry):\s*(.*)$/);
    if(!match)continue;
    const [,space,id,kind,body]=match;
    const control={id,kind,body,indent:space.length,lineIndex,disabled:/; disabled$/.test(body),label:body.replace(/; (?:selected|progress|active|disabled).*$/,"").trim()};
    if(kind==="slider"){
      const range=body.match(/value=(\d+), range=0\.\.(\d+)/);
      if(range){control.current=Number(range[1]);control.maximum=Number(range[2]);}
      control.label=body.split(/\s*value=/)[0].trim();
    }
    controls.push(control);
  }
  for(const [index,control] of controls.entries()){
    if(control.kind!=="slider")continue;
    // Scrollbar children share the indentation of research sliders after the last row.
    // Their adjacent native arrow buttons distinguish them from that row's slider.
    const arrows=controls.slice(index+1,index+3);
    control.scrollbar=arrows.length===2&&arrows.every(c=>c.kind==="button"&&c.indent===control.indent&&/^scroll (up|down|left|right)$/.test(c.label));
    if(control.scrollbar){control.label="列表滚动位置";continue;}
    const parent=controls.slice(0,index).reverse().find(c=>c.indent<control.indent);
    if(parent?.kind==="row"){
      control.rowId=parent.id;parent.sliderId=control.id;
      control.label=control.label||parent.label.replace(/\s*\|\s*[\d,]+$/,"");
    }
    if(!control.label&&lines.slice(0,control.lineIndex).some(line=>line.trim()==="Number of items"))control.label="Number of items · 数量";
    control.label=control.label||`数值滑条 ${control.id}`;
  }
  return controls;
}
function renderSingularitySliders(){
  let panel=$("singularity-sliders");
  if(!panel){panel=document.createElement("section");panel.id="singularity-sliders";panel.className="native-sliders";$("board").before(panel);}
  panel.replaceChildren();panel.hidden=true;
  const attempt=state.active;
  if(attempt?.condition!=="text"||attempt.observation.interface_profile!=="singularity-native-visible-widgets-v0")return;
  const sliders=singularityControls(attempt.observation.board_text).filter(c=>c.kind==="slider"&&c.maximum!==undefined);
  if(!sliders.length)return;
  panel.hidden=false;
  const help="拖动滑条或直接输入目标值，再点“应用数值”。编辑时不消耗步数，每次提交消耗一次决策。"+(attempt.observation.board_text.startsWith("Current panel: ResearchScreen.")?"研究项目的“查看详情”不会分配 CPU。":"");
  panel.append(textNode("h3","调整当前可见滑条"),textNode("p",help,"small"));
  for(const control of sliders){
    const form=document.createElement("form");form.className="native-slider";form.dataset.control=control.id;
    const title=textNode("strong",control.label),hint=textNode("span",`当前 ${control.current} · 可设 0–${control.maximum}${control.maximum===0?" · 当前不可调整":""}`,"small");
    const range=document.createElement("input");range.type="range";range.setAttribute("aria-label",control.label+" 滑条");
    const number=document.createElement("input");number.type="number";number.setAttribute("aria-label",control.label+" 目标值");number.required=true;
    const submit=textNode("button","应用数值");submit.type="submit";submit.className="secondary";submit.setAttribute("aria-label","应用 "+control.label+" 数值");
    for(const input of [range,number]){input.min="0";input.max=String(control.maximum);input.step="1";input.value=String(control.current);}
    for(const element of [range,number,submit]){element.dataset.controlDisabled=String(control.disabled||control.maximum===0);element.disabled=state.busy||element.dataset.controlDisabled==="true";}
    range.oninput=()=>{number.value=range.value;};
    number.oninput=()=>{if(number.validity.valid)range.value=number.value;};
    form.onsubmit=e=>{e.preventDefault();if(!form.reportValidity())return;const value=number.valueAsNumber;if(value===control.current){notice("数值未改变。请设置新的目标值后再提交。");return;}void perform({type:"set_value",control:control.id,value});};
    form.append(title,hint,range,number,submit);panel.append(form);
  }
}
function renderFields(){
  const spec=state.active?.schemas.find(s=>s.function.name===$("action-type").value)?.function;if(!spec)return;
  $("action-description").textContent=spec.description;$("action-fields").replaceChildren();
  for(const [name,prop] of Object.entries(spec.parameters.properties||{})){
    const label=textNode("label",fields[name]||name);let input;
    if(name==="control"&&!prop.enum&&state.active.observation.interface_profile==="singularity-native-visible-widgets-v0"){
      input=document.createElement("select");const placeholder=textNode("option","请选择当前可见控件");placeholder.value="";placeholder.disabled=true;placeholder.selected=true;input.append(placeholder);
      const wanted={click:["button","row"],set_value:["slider"],type_text:["entry"]}[spec.name]||[];
      for(const control of singularityControls(state.active.observation.board_text)){
        if(!wanted.includes(control.kind))continue;
        const detail=control.kind==="slider"?`${control.label} · 当前 ${control.current}，范围 0–${control.maximum}`:control.sliderId?`查看详情 · ${control.label}`:control.body;
        const option=textNode("option",`${control.id} · ${detail}`);option.value=control.id;option.disabled=control.disabled;
        if(control.maximum!==undefined){option.dataset.current=String(control.current);option.dataset.maximum=String(control.maximum);}
        input.append(option);
      }
      input.onchange=()=>{const value=document.querySelector('#action-fields [name="value"]'),option=input.selectedOptions[0];if(value&&option?.dataset.current!==undefined){value.max=option.dataset.maximum;value.value=option.dataset.current;}};
    }else if(prop.enum){input=document.createElement("select");for(const x of prop.enum){const option=textNode("option",choices[x]||x);option.value=x;input.append(option);}}
    else{input=document.createElement("input");input.type=prop.type==="integer"?"number":"text";if(prop.type==="integer"){input.step="1";input.min=prop.minimum??0;if(prop.maximum!==undefined)input.max=prop.maximum;input.value=(prop.minimum??0)<=0&&(prop.maximum??Infinity)>=0?0:prop.minimum??0;}}
    input.name=name;input.required=true;input.id="action-field-"+name;input.setAttribute("aria-label",fields[name]||name);label.htmlFor=input.id;label.append(input);$("action-fields").append(label);
  }
}
function updateClock(){if(!state.active?.deadline)return;const n=Math.max(0,Math.ceil((state.active.deadline*1000-Date.now()-state.serverOffset)/1000));$("clock").textContent=`${String(Math.floor(n/60)).padStart(2,"0")}:${String(n%60).padStart(2,"0")}`;}
async function perform(action){
  if(!state.active||state.busy||state.pending)return;
  if(action.type==="finish"&&!await confirmAction("现在结束本题？","系统会判定当前状态；尚未达成目标会记为未完成。本题提交后不能重做。"))return;
  pendingSave({aid:state.active.attempt_id,alias:state.session.participant.alias,request:{request_id:requestId(),observation_id:state.active.observation.observation_id,action}});
  await resend();
}
async function resend(){
  if(!state.pending||state.busy)return;
  if(state.pending.alias!==state.session?.participant?.alias){pendingSave(null);return;}
  setBusy(true);$("connection").textContent="正在执行…";$("reconnect").hidden=true;
  try{
    const p=state.pending;const reply=await api(`/api/attempts/${p.aid}/actions`,p.request);pendingSave(null);notice("");
    if(reply.observation.ended){await refresh();notice("本题记录已保存："+(reasons[reply.observation.result?.stop_reason]||"已结束"));}
    else if(state.active?.attempt_id===reply.attempt_id)renderAttempt({...state.active,observation:reply.observation});else await refresh();
  }catch(e){
    if(["attempt_finished","stale_observation"].includes(e.code)){pendingSave(null);await refresh();notice(e.message);}
    else if(e.status&&e.status<500&&e.status!==408&&e.code!=="action_pending"){pendingSave(null);notice(e.message,true);}
    else{notice("连接中断或上一步尚未确认。请点击“恢复连接”确认结果。",true);$("reconnect").hidden=false;$("connection").textContent="等待连接";}
  }finally{setBusy(false);}
}
function point(event){const img=$("game-image"),r=img.getBoundingClientRect(),o=state.active?.observation.image;if(!o||event.clientX<r.left||event.clientX>=r.right||event.clientY<r.top||event.clientY>=r.bottom)return null;return [Math.floor((event.clientX-r.left)*o.width/r.width),Math.floor((event.clientY-r.top)*o.height/r.height)];}
let down=null;
$("viewport").addEventListener("contextmenu",e=>e.preventDefault());
$("viewport").addEventListener("pointerdown",e=>{if(state.busy||state.pending||!state.active)return;const p=point(e);if(!p)return;e.preventDefault();$("viewport").focus({preventScroll:true});down={point:p,pointer:e.pointerId};$("viewport").setPointerCapture(e.pointerId);$("pointer-hint").textContent=$("pointer-mode").value==="drag"?"移动到目标位置后松开。":"松开鼠标执行操作。";});
$("viewport").addEventListener("pointercancel",()=>{down=null;});
$("viewport").addEventListener("pointerup",e=>{if(!down||down.pointer!==e.pointerId)return;const from=down.point;down=null;const to=point(e);if(!to){$("pointer-hint").textContent="操作已取消，请在游戏图片内选择位置。";return;}const mode=$("pointer-mode").value,button=$("mouse-button").value;const action=mode==="drag"?{type:"drag",from,to,duration_ms:350,button}:mode==="move"?{type:"mouse_move",x:to[0],y:to[1]}:{type:"click",x:to[0],y:to[1],button,count:mode==="double"?2:1};void perform(action);});
const keyMap={ArrowUp:"up",ArrowDown:"down",ArrowLeft:"left",ArrowRight:"right"," ":"space",Enter:"enter",Escape:"escape",u:"u",r:"r",z:"z"};
$("viewport").addEventListener("keydown",e=>{if(keyMap[e.key]&&!e.repeat&&!e.metaKey&&!e.ctrlKey&&!e.altKey){e.preventDefault();void perform({type:"key_press",key:keyMap[e.key]});}});
$("key-button").onclick=()=>perform({type:"key_press",key:$("key-select").value});$("wait-button").onclick=()=>perform({type:"wait",duration_ms:1000});$("finish-button").onclick=()=>perform({type:"finish"});$("reconnect").onclick=async()=>{if(state.pending)await resend();else await safeRefresh();};
$("action-type").onchange=renderFields;
$("action-form").onsubmit=async e=>{e.preventDefault();const spec=state.active.schemas.find(s=>s.function.name===$("action-type").value).function,action={type:spec.name};for(const [name,prop]of Object.entries(spec.parameters.properties)){const v=e.target.elements.namedItem(name).value;action[name]=prop.type==="integer"?Number(v):v;}await perform(action);};
function controlSave(value){state.pendingControl=value;try{if(value)sessionStorage.setItem("screenplay.control",JSON.stringify(value));else sessionStorage.removeItem("screenplay.control");}catch{}$("control-retry").hidden=!value;}
async function retryControl(){
  const pending=state.pendingControl;if(!pending||state.busy)return false;
  if(pending.participant!==state.session?.participant?.id){controlSave(null);return false;}
  setBusy(true);
  try{const data=await api("/api/"+pending.kind,pending.request);controlSave(null);renderSession({role:"participant",...data});notice(pending.kind==="pause"?"已暂离，进度已保存。现在可以关闭页面，稍后用原邀请码返回。":pending.kind==="resume"?"已恢复参与。":"已结束本次参与，记录已保留。");return true;}
  catch(e){if(e.status&&e.status<500){controlSave(null);await safeRefresh();}notice(e.message||"连接中断，请确认上次操作。",true);return false;}finally{setBusy(false);}
}
async function participation(kind,accepted=false){
  if(state.busy)return false;
  if(state.pending){await resend();if(state.pending){notice("请先恢复连接，确认上一步动作。",true);return false;}}
  if(state.pendingControl){notice("请先确认上次暂离／继续操作。",true);return state.pendingControl.kind===kind?retryControl():false;}
  const current=state.active||state.session.paused_attempt;
  controlSave({kind,participant:state.session.participant.id,request:{request_id:requestId(),attempt_id:current?.attempt_id||null,revision:state.session.participant.control_revision,accepted}});
  return retryControl();
}
async function takeBreak(){return participation("pause");}
async function withdraw(){if(!await confirmAction("结束参与本研究？","日常休息请使用“暂离，稍后继续”。结束参与会关闭当前题并记为未评分中断，已提交结果保留。"))return;try{await refresh();pendingSave(null);controlSave(null);await participation("withdraw",true);}catch(e){notice(e.message,true);}}
$("withdraw-button").onclick=withdraw;$("withdraw-between").onclick=withdraw;
$("pause-button").onclick=takeBreak;$("pause-between").onclick=takeBreak;$("control-retry").onclick=retryControl;
$("consent-button").onclick=async()=>{if(!$("consent-check").checked){notice("请先勾选阅读确认。",true);return;}try{await api("/api/consent",{accepted:true});notice("");await refresh();}catch(e){notice(e.message,true);}};
$("start-button").onclick=async()=>{if(state.busy)return;if(state.session.participant.withdrawn){if(await confirmAction("恢复参与研究？","确认愿意继续参与。已有评分会保留，未完成的题目可以继续安排。"))await participation("resume",true);return;}if(state.session.participant.paused){await participation("resume");return;}try{setBusy(true);notice("正在准备原生环境…");const attempt=await api("/api/attempts",{});renderAttempt(attempt);await refresh();notice("");}catch(e){notice(e.message,true);await safeRefresh();}finally{setBusy(false);}};
$("load-history").onclick=async()=>{if(!state.active)return;try{const h=await api(`/api/attempts/${state.active.attempt_id}/history`);const container=$("history-content");container.replaceChildren();for(const o of h.observations){const article=document.createElement("article");article.className="history-item";article.append(textNode("strong",`盘面 ${o.observation_id}`));if(o.image){const img=document.createElement("img");img.src="data:image/png;base64,"+o.image.base64;img.alt=`历史盘面 ${o.observation_id}`;article.append(img);}if(o.board_text)article.append(textNode("pre",o.board_text));container.append(article);}container.append(textNode("pre",h.actions.map(a=>`${a.observation_id+1}. ${JSON.stringify(a.action)}`).join("\n")||"暂无操作", "history-actions"));}catch(e){notice(e.message,true);}};

async function login(kind, code){try{await api("/api/login",{kind,code:code.trim()});notice("");await refresh();if(state.pending)await resend();}catch(e){notice(e.message,true);}}
$("join-form").onsubmit=e=>{e.preventDefault();void login("participant",$("invite-code").value);};$("admin-login-form").onsubmit=e=>{e.preventDefault();void login("admin",$("admin-code").value);};
$("logout").onclick=async()=>{try{if(state.session?.role==="participant"&&!state.session.participant.done&&!state.session.participant.withdrawn&&!state.session.participant.paused){if(!await takeBreak())return;}await api("/api/logout",{});pendingSave(null);controlSave(null);location.href="/";}catch(e){notice(e.message,true);}};

let pickerBuilt=false;
async function loadAdmin(){
  if(!pickerBuilt){
    const data=await api("/api/admin/catalog");state.catalog=data.tasks;state.participantOrigin=data.participant_origin||location.origin;
    state.invitationPresets=data.invitation_presets||[{id:"original_text45",condition:"text",task_ids:data.tasks.filter(t=>t.text_supported).map(t=>t.task_id)}];
    $("select-new-text").disabled=!state.invitationPresets.some(p=>p.id==="new_text45"&&p.task_ids.length===45);
    $("task-picker").replaceChildren();
    for(const t of data.tasks){
      const label=document.createElement("label");label.className="task-choice";
      const input=document.createElement("input");input.type="checkbox";input.value=t.task_id;input.dataset.text=t.text_supported?"1":"0";input.dataset.textGroup=t.text_group||"";input.onchange=countSelection;
      const span=textNode("span",t.task_id);span.append(textNode("small",`${t.game} · ${t.difficulty} · ${t.text_group==="new_text45"?"新增文本":t.text_supported?"原有文本":"图片"}`));label.append(input,span);$("task-picker").append(label);
    }
    const p=data.protocol;$("protocol-details").replaceChildren();
    const limits=data.tasks.filter(t=>t.text_group==="new_text45").map(t=>t.text_max_decisions);
    const entries=[["协议创建版本",p.version],["运行版本",data.app_version],["原有题目决策上限",p.max_decisions],["每题时间",`${p.wall_seconds} 秒`],["最近盘面",p.observation_window],["文本并发",p.max_text_workers]];
    if(limits.length)entries.splice(3,0,["新增文本题上限",`${Math.min(...limits)}–${Math.max(...limits)} 次，按题目设置`]);
    for(const [k,v]of entries)$("protocol-details").append(textNode("dt",k),textNode("dd",v));
    pickerBuilt=true;countSelection();
  }
  const data=await api("/api/admin/overview");updateStatistics(data);$("participant-rows").replaceChildren(...data.participants.map(p=>{const a=data.attempts.filter(x=>x.participant_id===p.id),n=a.filter(x=>x.status==="scored").length;const tr=document.createElement("tr");for(const x of[p.alias,p.assignment.length,n,p.withdrawn?"已结束参与":p.paused_at?"暂离中":a.some(x=>x.status==="active")?"作答中":n===p.assignment.length?"已结束":p.consent?"题间休息":"未开始"])tr.append(textNode("td",x));return tr;}));
}

const decimal = value => value===null||value===undefined?"—":Number(value).toFixed(1);
const percent = value => value===null||value===undefined?"—":(value*100).toFixed(1)+"%";
let reportData=null, reportPage=0;
function updateStatistics(data){
  reportData=data;
  const select=$("report-participant"),previous=select.value;
  select.replaceChildren(textNode("option","全部受试者"));select.options[0].value="";
  for(const p of data.participants){const option=textNode("option",p.alias);option.value=p.id;select.append(option);}
  select.value=data.participants.some(p=>p.id===previous)?previous:"";
  $("stats-updated").textContent=(data.protocol.actor==="validation"?"开发验证数据 · ":"")+"更新于 "+new Date(data.exported_at).toLocaleTimeString();
  renderStatistics();
}
function statisticRows(target,items){
  $(target).replaceChildren(...items.map(r=>{const tr=document.createElement("tr");for(const value of [r.label,`${r.correct_count} / ${r.scored_count} / ${r.assigned_count}`,percent(r.accuracy),decimal(r.mean_elapsed_seconds),decimal(r.mean_decisions),decimal(r.mean_success_elapsed_seconds),decimal(r.mean_success_decisions)])tr.append(textNode("td",value));return tr;}));
  if(!items.length){const tr=document.createElement("tr"),td=textNode("td","当前筛选下尚无分配题目。");td.colSpan=7;tr.append(td);$(target).append(tr);}
}
function renderStatistics(){
  if(!reportData?.report)return;
  const pid=$("report-participant").value||null,condition=$("report-condition").value;
  const view=reportData.report.views.find(v=>v.participant_id===pid&&v.condition===condition);if(!view)return;
  const m=view.overall;
  $("stat-accuracy").textContent=percent(m.accuracy);$("stat-correct").textContent=`答对 ${m.correct_count} · 答错 ${m.incorrect_count}`;
  $("stat-time").textContent=decimal(m.mean_elapsed_seconds)+(m.elapsed_n?" 秒":"");$("stat-time-n").textContent=`有效计时 ${m.elapsed_n} 份 · 答对题 ${decimal(m.mean_success_elapsed_seconds)} 秒`;
  $("stat-steps").textContent=decimal(m.mean_decisions);$("stat-step-n").textContent=`有效步数 ${m.decisions_n} 份 · 答对题 ${decimal(m.mean_success_decisions)} 步`;
  $("stat-coverage").textContent=`${m.scored_count} / ${m.assigned_count}`;$("stat-unscored").textContent=`未评分 ${m.unscored_count} · 作答中 ${m.active_count} · 暂离 ${m.paused_count||0}`;
  $("stats-quality").textContent=`已评分记录中：计时缺失 ${m.elapsed_missing_n} 份、旧记录时间估算 ${m.estimated_elapsed_n} 份、步数缺失 ${m.decisions_missing_n} 份。另保留 ${m.interrupted_attempt_count} 次中断记录。各均值按实际有效样本计算，缺失不补零。`;
  statisticRows("condition-stat-rows",view.by_condition);
  const group=$("report-group").value;$("group-stat-title").textContent="按"+$("report-group").selectedOptions[0].textContent+"统计";
  let groups=view["by_"+group];if(group==="difficulty")groups=[...groups].sort((a,b)=>(["easy","medium","hard"].indexOf(a.key))-["easy","medium","hard"].indexOf(b.key));
  statisticRows("group-stat-rows",groups);
  const rows=reportData.report.rows.filter(r=>(pid===null||r.participant_id===pid)&&(condition==="all"||r.condition===condition));
  const pages=Math.max(1,Math.ceil(rows.length/50));reportPage=Math.min(reportPage,pages-1);
  const timing={monotonic_excluding_pauses:"扣除暂离",paused_monotonic:"已暂停计时",paused_checkpoint:"暂停时记录",monotonic:"精确计时",budget_limit:"时间上限",legacy_wall_clock_estimate:"旧记录估算",running_monotonic:"计时中",unavailable_after_restart:"中断后未知",not_started:"尚未启动",unavailable:"无记录"};
  const status={paused:"已暂离",not_started:"未作答",starting:"启动中",active:"作答中",interrupted:"中断 · 未评分",withdrawn_unstarted:"退出 · 未作答"};
  $("task-result-rows").replaceChildren(...rows.slice(reportPage*50,(reportPage+1)*50).map(r=>{const tr=document.createElement("tr");const outcome=r.correct===true?"正确":r.correct===false?"错误"+(r.stop_reason==="wall_budget_exhausted"?" · 超时":""):status[r.status]||r.status;for(const value of [r.participant,`${r.question_number} · ${r.task_id}`,r.game,r.difficulty_label,r.condition==="gui"?"图片":"文本",outcome,decimal(r.elapsed_seconds),r.decisions??"—",timing[r.elapsed_source]||"—"])tr.append(textNode("td",value));return tr;}));
  $("report-page").textContent=`第 ${reportPage+1} / ${pages} 页 · ${rows.length} 道分配题`;
  $("report-prev").disabled=reportPage===0;$("report-next").disabled=reportPage+1>=pages;
}
for(const id of ["report-participant","report-condition","report-group"])$(id).onchange=()=>{reportPage=0;renderStatistics();};
$("report-prev").onclick=()=>{reportPage=Math.max(0,reportPage-1);renderStatistics();};
$("report-next").onclick=()=>{reportPage++;renderStatistics();};

function countSelection(){
  const all=[...document.querySelectorAll("#task-picker input")],condition=$("assignment-condition").value;
  for(const x of all){x.disabled=condition!=="gui"&&x.dataset.text!=="1";if(x.disabled)x.checked=false;}
  const selected=all.filter(x=>x.checked),newText=selected.filter(x=>x.dataset.textGroup==="new_text45");
  const completeNew=condition==="text"&&selected.length===45&&newText.length===45;
  $("selection-count").textContent=`已选择 ${selected.length} 题 · ${condition==="gui"?"图片":condition==="text"?"文本":"混合"}${completeNew?" · 新增 45 题（3 个项目各 15 题）":""}`;
  $("assignment-summary").textContent=condition!=="gui"&&newText.length?"新增文本题包含 Singularity、OpenTTD 和 Enigma，使用与本轮模型评测一致的各题步数上限。生成后复制链接，发送给受试者。":"生成邀请后，复制专属作答链接并发送给受试者。已有邀请码和作答记录不会改变。";
}
function selectInvitationPreset(id){
  const preset=state.invitationPresets.find(p=>p.id===id);if(!preset)return;
  $("assignment-condition").value=preset.condition;const ids=new Set(preset.task_ids);
  for(const x of document.querySelectorAll("#task-picker input"))x.checked=ids.has(x.value);
  countSelection();
}
$("assignment-condition").onchange=countSelection;
$("select-new-text").onclick=()=>selectInvitationPreset("new_text45");
$("select-paired").onclick=()=>selectInvitationPreset("original_text45");
$("select-all").onclick=()=>{$("assignment-condition").value="gui";for(const x of document.querySelectorAll("#task-picker input"))x.checked=true;countSelection();};
$("select-none").onclick=()=>{for(const x of document.querySelectorAll("#task-picker input"))x.checked=false;countSelection();};
$("assignment-form").onsubmit=async e=>{e.preventDefault();try{const task_ids=[...document.querySelectorAll("#task-picker input:checked")].map(x=>x.value);const v=await api("/api/admin/invitations",{alias:$("alias").value,task_ids,condition:$("assignment-condition").value,seed:Number($("seed").value)});$("invitation-result").hidden=false;$("invitation-alias").textContent=`${v.alias} · ${v.task_count} 题`;$("invitation-code").value=v.invitation_code;$("invitation-link").value=state.participantOrigin+"/join#code="+encodeURIComponent(v.invitation_code);notice("邀请已创建。请保存并发送给对应受试者。");await loadAdmin();}catch(e){notice(e.message,true);}};
$("copy-invitation").onclick=async()=>{try{await navigator.clipboard.writeText($("invitation-link").value);notice("作答链接已复制。");}catch{$("invitation-link").select();notice("请选择并复制此作答链接。");}};$("refresh-admin").onclick=()=>loadAdmin().catch(e=>notice(e.message,true));
async function safeRefresh(){if(state.refreshing)return;state.refreshing=true;try{await refresh();if(state.networkNotice){notice("");state.networkNotice=false;$("reconnect").hidden=!state.pending;}}catch(e){if(e.status===401){state.active=null;$("logout").hidden=true;show(location.pathname==="/admin"?"admin-login-view":"join-view");notice(e.message,true);}else{state.networkNotice=true;notice(e.message||"连接中断，请稍后恢复。",true);if(state.active){$("connection").textContent="等待连接";$("reconnect").hidden=false;}}}finally{state.refreshing=false;}}
async function init(){
  show(location.pathname==="/admin"?"admin-login-view":"join-view");
  try{state.pending=JSON.parse(sessionStorage.getItem("screenplay.pending")||"null");controlSave(JSON.parse(sessionStorage.getItem("screenplay.control")||"null"));}catch{}
  const code=new URLSearchParams(location.hash.slice(1)).get("code");if(code){$("invite-code").value=code;history.replaceState(null,"",location.pathname);}
  if(location.pathname==="/developer"){show("developer-view");return;}
  try{await refresh();if(state.pending&&state.session?.role==="participant"){notice("正在确认断线前的最后一步…");await resend();}}
  catch(e){if(e.status===401)show(location.pathname==="/admin"?"admin-login-view":"join-view");else notice(e.message||"暂时无法连接服务。",true);}
  setInterval(updateClock,1000);setInterval(()=>{if(state.session?.role==="participant"&&state.active&&!state.busy&&!state.pending)void safeRefresh();},3000);
}
void init();
