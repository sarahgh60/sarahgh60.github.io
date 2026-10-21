// Folio 2026 · hero-gl.js · decorative: the page is complete without it
const d=document,H=d.documentElement,w=window,M=Math,now=()=>performance.now(),$=(s,r=d)=>r.querySelector(s),$$=(s,r=d)=>[...r.querySelectorAll(s)],
cl=(v,a=0,b=1)=>M.min(b,M.max(a,v)),ss=(a,b,x)=>(x=cl((x-a)/(b-a)),x*x*(3-2*x)),raf=f=>requestAnimationFrame(f),
ok=()=>H.dataset.motion=='full'&&H.dataset.contrast!='more'&&navigator.connection?.saveData!==!0,
EZ='cubic-bezier(.65,0,.35,1)',EO='cubic-bezier(.2,.8,.2,1)',on=(t,e,f,o={passive:!0})=>t.addEventListener(e,f,o),
hex=s=>[0,2,4].map(i=>parseInt(s.substr(i,2),16)/255),
NZ='precision highp float;float hs(vec2 p){vec3 q=fract(p.xyx*.1031);q+=dot(q,q.yzx+33.33);return fract((q.x+q.y)*q.z);}float vn(vec2 p){vec2 i=floor(p),f=fract(p);f*=f*(3.-2.*f);return mix(mix(hs(i),hs(i+vec2(1,0)),f.x),mix(hs(i+vec2(0,1)),hs(i+1.),f.x),f.y);}',
// no software GL (?gl=any allows it)
SW=/[?&]gl=any\b/.test(location.search),
ctx=(c,a)=>{const o={alpha:a,antialias:!1,depth:!1,stencil:!1,powerPreference:'low-power',failIfMajorPerformanceCaveat:!SW};return c.getContext('webgl2',o)||c.getContext('webgl',o)};
// async link (KHR_parallel_shader_compile) → uniform setter | null
function prog(g,fs){const P=g.createProgram(),U={};
[[35633,'attribute vec2 p;void main(){gl_Position=vec4(p,0,1);}'],[35632,NZ+fs]].forEach(([t,s])=>{const S=g.createShader(t);g.shaderSource(S,s);g.compileShader(S);g.attachShader(P,S)});
g.bindAttribLocation(P,0,'p');g.linkProgram(P);const K=g.getExtension('KHR_parallel_shader_compile'),
done=()=>{if(g.isContextLost()||!g.getProgramParameter(P,35714))return null;g.useProgram(P);
g.bindBuffer(34962,g.createBuffer());g.bufferData(34962,new Float32Array([-1,-1,3,-1,-1,3]),35044);g.enableVertexAttribArray(0);g.vertexAttribPointer(0,2,5126,!1,0,0);
for(let i=g.getProgramParameter(P,35718);i--;){const a=g.getActiveUniform(P,i);U[a.name.replace('[0]','')]=[g.getUniformLocation(P,a.name),a.type]}
return(k,v)=>{const[l,t]=U[k]||[];l&&(t==35664?g.uniform2fv(l,v):t==35665?g.uniform3fv(l,v):t==35666?g.uniform4fv(l,v):t==35678?g.uniform1i(l,v):g.uniform1f(l,v))}};
return new Promise(r=>{if(!K)return r(done());const poll=()=>g.isContextLost()?r(null):g.getProgramParameter(P,37297)?r(done()):raf(poll);poll()})}
// Wash & Lamp
const WASH=`uniform vec2 u_res,u_lamp;uniform float u_scale,u_time,u_drift,u_seed,u_lampGain,u_bloom,u_pigMix,u_focusGain,u_theme,u_quality;
uniform vec4 u_region,u_focus,u_mask[10];uniform vec3 u_pigA,u_pigB,u_glaze,u_dab[12],u_dabPig,u_lampCol;
float fbm(vec2 p,int o){float v=0.,a=.5;for(int i=0;i<5;i++){if(i>=o||i>2&&u_quality<.5)break;v+=a*vn(p);p=mat2(1.6,1.2,-1.2,1.6)*p+7.3;a*=.5;}return v/(1.-2.*a);}
float sb(vec2 p,vec2 b){vec2 q=abs(p)-b;return length(max(q,0.))+min(max(q.x,q.y),0.);}
float th(vec2 p){p/=u_scale;return .55*vn(p*.29)+.3*vn(p*.63)+.15*vn(p*1.4);}
void main(){
vec2 px=vec2(gl_FragCoord.x,u_res.y-gl_FragCoord.y),hb=u_region.zw*.5;float s=u_scale,a=0.;vec3 pg=u_pigB;
float rn=-sb(px-u_region.xy-hb,hb)/min(hb.x,hb.y);
if(rn>-.6){vec2 q=(px-u_region.xy)/min(u_region.z,u_region.w)*2.2+u_seed,k=vec2(fbm(q*1.3,4),fbm(q*1.3+5.2,4));q+=.55*k+.02*u_drift;
float v=6.*smoothstep(-.4,.3,rn)-2.6+(fbm(q,4)-.51)*10.8,t=mix(6.48,.08,u_bloom),z=v-t;
a=smoothstep(0.,.06,z)*(.13+.14*(1.-smoothstep(0.,.12,z))+.09*(1.-smoothstep(0.,.7,z)))*(.85+.3*vn(q*7.));
pg=mix(u_pigA,u_pigB,clamp(u_pigMix*1.3-.15+(k.x-.51)*3.,0.,1.));}
float A=0.,S=-1.;
for(int i=0;i<12;i++){vec3 b=u_dab[i];float g=u_time-b.z,l=length(px-b.xy),r=(18.+38.*smoothstep(0.,1.4,g))*s;
if(g<0.||g>6.||l>r*1.4)continue;
float n=(l+8.*s*(fbm(px/(60.*s)+float(i)*7.,3)-.51)*10.)/r;
S=max(S,1.-n);A=max(A,smoothstep(1.,.95,n)*(1.-smoothstep(3.5,6.,g)));}
float dc=A*(.12+.11*(1.-smoothstep(0.,.09,S)));
pg=mix(pg,u_dabPig,dc/max(a+dc,.001));a+=dc*(1.-a);
float h=th(px),m=1.;a*=(.82+.36*h*u_quality)*mix(1.25,.65,u_theme);
for(int i=0;i<10;i++)m*=smoothstep(0.,28.*s,sb(px-u_mask[i].xy,u_mask[i].zw));
a*=m;
float fd=sb(px-u_focus.xy-vec2(3,4)*s,u_focus.zw),f=0.,pd=mix(-.6*u_focus.w,11.*s,u_focusGain);
if(fd<pd+16.*s){fd+=12.*s*(fbm(px/(44.*s)+u_seed,3)-.51)*6.;f=(1.-smoothstep(pd-2.5*s,pd,fd))*step(.01,u_focusGain);}
float ga=f*(.12+.2*smoothstep(pd-9.*s,pd,fd))*mix(1.,1.3,u_theme);
vec2 L=(u_lamp*u_res-px)/u_res.y,ed=min(px,u_res-px);float e=dot(L,L),fe=smoothstep(0.,60.*s,min(ed.x,ed.y))*u_lampGain,pl=exp(-e*6.)*mix(.1,.07,u_theme)*fe*smoothstep(0.,20.*s,sb(px-u_mask[9].xy,u_mask[9].zw));
vec4 o=vec4(u_lampCol*pl,pl);
if(u_quality>.5&&e<.5){vec3 l=normalize(vec3(L,.22)),n=normalize(vec3(h-th(px+vec2(1.5*s,0)),h-th(px+vec2(0,1.5*s)),.12));
float sh=(dot(n,l)-l.z)*.075*exp(-e*12.)*fe*m;
o=sh>0.?o*(1.-sh)+vec4(u_lampCol*sh,sh):o*(1.+sh)-vec4(mix(vec3(.1,.08,.07),vec3(0,.03,.08),u_theme)*sh,sh);}
vec4 c=vec4(pg*a,a);c=vec4(u_glaze*ga,ga)+c*(1.-ga);c+=o*(1.-c.a);
c.rgb+=(hs(gl_FragCoord.xy)-.5)/255.;gl_FragColor=c;}`;
const FIN={lampGain:1,bloom:.7,pigMix:1,focusGain:1},
MASKS=['.titleblock','.titleblock__hint','.hero__name','.role','.thesis','.hero__links','.scope','.scope-line','.hero__cue','.hero__dim text'];
function wash(hero,intro,clk){const cv=$('.hero__gl',hero),g=cv&&ctx(cv,!0);if(!g)return;
const dabs=new Float32Array(36).fill(-99),lamp=[.16,.1],seed=[3,7,11,29,41,61][M.random()*6|0],t0=now(),mq=q=>w.matchMedia(q).matches;
let u,s,W,Ht,rq=0,vis=!d.hidden,inv=!0,dead=0,off=0,odd=0,lt=0,ld=0,n=0,ft=[],mn=99,rt,lT=[.16,.1],last=[-1e3,-1e3,-1e4],
Q=mq('(pointer:coarse)')||navigator.hardwareConcurrency<=4||navigator.deviceMemory<=4?0:1,
tw=intro,E=x=>1-(1-cl(x))**3;
const val=e=>tw?{lampGain:E(e/1500),bloom:e<600?.45*E(e/700):.45+.25*E((e-600)/900),pigMix:E((e-600)/1e3),focusGain:E((e-1250)/900)}:FIN,
statics=()=>{const b=H.dataset.theme=='blueprint',c=b?['7fb2e5','7fb2e5','fb794a','7fb2e5','9fc3ea']:['d4896e','6fb07d','ec4f27','6fb07d','fff1dc'];
['pigA','pigB','glaze','dabPig','lampCol'].forEach((k,i)=>u('u_'+k,hex(c[i])));u('u_theme',+b);u('u_quality',Q);u('u_seed',seed)},
draw=()=>{if(!u)return;const e=clk(),v=val(e);for(const k in v)u('u_'+k,v[k]);
u('u_time',(now()-t0)/1e3);u('u_drift',M.min(e,8e3)/1e3);u('u_lamp',lamp);u('u_dab',dabs);g.drawArrays(4,0,3)},
size=()=>{if(!u)return;const r=cv.getBoundingClientRect(),R=(e,p=0)=>{const b=e&&e.getBoundingClientRect();return b&&b.width?[(b.left-r.left+b.width/2)*s,(b.top-r.top+b.height/2)*s,(b.width/2+p)*s,(b.height/2+p)*s]:[-1e5,-1e5,0,0]};
s=M.min(w.devicePixelRatio||1,1.5)*(Q?.66:.5);W=cv.width=M.max(1,M.round(r.width*s));Ht=cv.height=M.max(1,M.round(r.height*s));g.viewport(0,0,W,Ht);
const f=R($('.d-frame',hero));u('u_res',[W,Ht]);u('u_scale',s);u('u_region',[f[0]-f[2],f[1]-f[3],f[2]*2,f[3]*2]);u('u_focus',R($('.d-lead',hero)));
u('u_mask',MASKS.flatMap(q=>R($(q,hero),2)));hero.style.setProperty('--fh',$('.hero__frame',hero).offsetHeight+'px');draw()},
stop=()=>{cancelAnimationFrame(rq);rq=0},
kick=()=>{if(!rq&&vis&&inv&&!dead&&!off&&u){lt=0;rq=raf(frame)}},
frame=t=>{rq=0;if(t-ld<13){rq=raf(frame);return}ld=t;const e=clk(),dx=lT[0]-lamp[0],dy=lT[1]-lamp[1];lamp[0]+=dx*.06;lamp[1]+=dy*.06;
const busy=e<8e3||M.hypot(dx*W,dy*Ht)/s>.5;if(!busy&&now()-last[2]>6e3)return draw();
rq=raf(frame);if(!busy&&(odd^=1))return;
if(busy&&lt&&++n>5){const dt=t-lt;mn=M.min(mn,dt);ft.push(dt);ft.length>30&&ft.shift();const av=ft.reduce((a,b)=>a+b)/ft.length;
if(ft.length==30&&av>M.max(28,mn*1.68)){dead=1;tw=0;stop();return draw()}
if(ft.length==30&&Q&&av>M.max(20,mn*1.2)){Q=0;ft=[];statics();size()}}
lt=busy?t:0;draw()},
setup=()=>prog(g,WASH).then(f=>{u=f;u?(statics(),size(),hero.dataset.gl='on',kick()):fail()}),
dab=(x,y,t)=>{let i=0;for(let j=3;j<36;j+=3)dabs[j+2]<dabs[i+2]&&(i=j);(t-t0)/1e3-dabs[i+2]>1.6&&(dabs.set([x*s,y*s,(t-t0)/1e3],i),last=[x,y,t])},
xy=e=>{const r=cv.getBoundingClientRect();return[e.clientX-r.left,e.clientY-r.top,r]};
on(cv,'webglcontextlost',e=>{e.preventDefault();u=0;stop();delete hero.dataset.gl},{});
on(cv,'webglcontextrestored',()=>{tw=0;setup()});
const fail=()=>{delete hero.dataset.gl;delete hero.dataset.wash};
on(d,'visibilitychange',()=>{vis=!d.hidden;vis?kick():stop()});
new IntersectionObserver(([x])=>{inv=x.isIntersecting;inv?kick():stop()}).observe(hero);
new ResizeObserver(()=>{clearTimeout(rt);rt=setTimeout(size,150)}).observe(hero);
d.fonts?.ready.then(size);
on(d,'folio:prefs',()=>{off=!ok();off?(stop(),delete hero.dataset.gl):u&&(statics(),draw(),hero.dataset.gl='on',kick())});
on(hero,'pointermove',e=>{if(e.pointerType=='touch'||off)return;const[x,y,r]=xy(e),t=now();lT=[x/r.width,y/r.height];
M.hypot(x-last[0],y-last[1])>=28&&t-last[2]>=120&&dab(x,y,t);kick()});
on(hero,'pointerdown',e=>{if(e.pointerType=='touch'){const[x,y]=xy(e);dab(x,y,now());kick()}});
on(hero,'pointerleave',()=>{lT=[.16,.1];kick()});
setup();return{fin(){tw=0;draw();kick()},ok:()=>!!u}}
// the plot: plan → app home → org chart, on one WAAPI clock
function plot(hero,svg,G,clk){
const A=[],D=[],J=[],seen=new Set(),ph=k=>$(`[data-phase=${k}]`,svg),P=ph('plan'),UI=ph('ui'),O=ph('org'),
pen=$('.pen',svg),rd=$('.pen__readout',pen),slot=$('.role__slot',hero),sc=$('.scale-cell',svg),dim=$('.hero__dim',hero),
an=(el,k,o,f='both')=>{const a=el.animate(k,{fill:f,easing:EZ,...o});A.push(a);seen.add(el);return a},
len=el=>{try{return el.getTotalLength()}catch{return 300}},
op=el=>el._o??=getComputedStyle(el).opacity,
at=(t,f)=>J.push(e=>e>=t&&(f(),1)),
inn=(els,t,st=40,trk=1,du)=>els.forEach((el,i)=>{const l=len(el),o={duration:du||cl(l*.35,120,420),delay:t+i*st},a=an(el,{strokeDashoffset:[1,0]},o);
getComputedStyle(el).fill!='none'&&an(el,{fillOpacity:[0,1]},o);trk&&D.push([el,a,l,o.delay,o.duration])}),
out=(els,t,st=15)=>els.forEach((el,i)=>an(el,{strokeDashoffset:[0,-1]},{duration:300,delay:t+i*st},'forwards')),
fade=(els,t,st=25,up=1,du=320)=>els.forEach((el,i)=>an(el,{opacity:up?[0,op(el)]:[op(el),0]},{duration:du,delay:t+i*st,easing:EO},up?'both':'forwards')),
type=(el,t)=>{const s=el.textContent,du=s.length*16;seen.add(el);el.textContent='';J.push(e=>(el.textContent=s.slice(0,M.round(cl((e-t)/du)*s.length)),e>t+du));return s},
rest=(g,t)=>fade([...g.children].filter(el=>!seen.has(el)),t,18),
gone=(g,t)=>fade([...g.children].filter(el=>!el.hasAttribute('pathLength')),t,0,0,210),
txt=(g,t,st)=>fade($$('text',g).filter(x=>!seen.has(x)),t,st),
pl=(g,k='')=>$$('[pathLength]'+k,g),bb=el=>el.getBBox(),
tf=(a,b)=>`translate(${b.x-a.x}px,${b.y-a.y}px) scale(${b.width/a.width},${b.height/a.height})`,
fb='transform-box:fill-box;transform-origin:',
_=H.dataset.plot='playing',labels=[P,UI,O].map(g=>$('.drawing__label',g)),texts=labels.map((l,i)=>type(l,[140,700,1300][i])),
S0=sc.textContent,cards=pl(UI,'[y="240"]'),pods=$$('.d-pod',O),uiS=pl(UI),
Wd={architect:75,designer:100,lead:125},rs=k=>$(`[data-role=${k}]`,slot),pc=$('.role__pc',slot),
gh=$('.d-anchor',P).cloneNode(),dl=$$('line',dim),dt=$('text',dim);
let cur='architect',px=120,py=120,done=0,rq;
slot.dataset.active=cur;sc.textContent='1:50';sc.style.cssText=fb+'center';pen.style.display='block';
gh.removeAttribute('data-anchor');gh.setAttribute('class','d-ghost');gh.style.cssText=fb+'0 0';svg.insertBefore(gh,P);
const g0=bb(gh),card=bb(cards[0]),lead=bb($('.d-lead',O)),dS=type(dt,2060);
inn(pl(P,'.d-wall'),0,70);inn(pl(P,'.d-part'),300,80);inn(pl(P,'.d-thin'),380,55);inn(pl(P,'.d-door'),520,60);
an($('.d-anchor',P),{opacity:[0,0]},{duration:1});fade([gh],360,0,1,520);fade($$('.d-poche',P),300,0,1,500);txt(P,460,30);rest(P,400);
out(pl(P),600);gone(P,580);inn(uiS.slice(0,1),600,0,1,460);inn(uiS.slice(1),690,22);
an(gh,{transform:['none',tf(g0,card)]},{duration:520,delay:660});txt(UI,860,16);rest(UI,940);
out(uiS.filter(el=>!cards.includes(el)),1200,10);gone(UI,1180);
cards.forEach((c,i)=>{c.style.cssText=fb+'0 0';an(c,{transform:['none',tf(bb(c),bb(pods[i]))]},{duration:540,delay:1200+i*45},'forwards');
an(c,{opacity:[1,0]},{duration:220,delay:1600+i*45,easing:EO},'forwards')});
an(gh,{transform:[tf(g0,card),tf(g0,lead)]},{duration:560,delay:1230},'forwards');an(gh,{opacity:[1,0]},{duration:500,delay:1900,easing:EO},'forwards');
inn(pl(O,'.d-lead'),1300);inn(pl(O,'.d-corr'),1440);fade(pods.slice(0,3),1580,50,1,260);inn(pods.slice(3),1700);inn(pl(O,'.d-person'),1680,45,0);txt(O,1620,22);rest(O,1820);
inn(dl.slice(0,2),1800,40,0,200);inn(dl.slice(2,3),1880,0,0,620);inn(dl.slice(3,4),1880,0,0,160);inn(dl.slice(4),2440,0,0,160);
an(pen,{opacity:[0,1]},{duration:200});an(rd,{opacity:[1,0]},{duration:200,delay:1960},'forwards');
an(pen,{opacity:[1,0]},{duration:200,delay:2180,iterations:3,easing:'steps(2,jump-none)'},'forwards');
const role=(k,t)=>at(t,()=>{const o=rs(cur),n=rs(k),f=Wd[cur]+'%';slot.dataset.active=k;
an(o,{visibility:['visible','visible'],transform:['none','translateY(-75%)'],opacity:[1,0]},{duration:380,easing:EO},'none');
an(n,{transform:['translateY(75%)','none'],opacity:[0,1],fontStretch:[f,Wd[k]+'%']},{duration:620,easing:'cubic-bezier(.16,1,.3,1)'},'none');cur=k}),
flip=(s,t)=>{an(sc,{transform:['scaleY(1)','scaleY(0)','scaleY(1)']},{duration:280,delay:t,easing:'ease-in-out'},'none');at(t+140,()=>sc.textContent=s)};
role('designer',640);role('lead',1240);pc&&an(pc,{clipPath:['inset(0 100% 0 0)','inset(0 0% 0 0)']},{duration:520,delay:1760,easing:EO});
fade([sc],0,0,1,200);flip('1:1',640);flip(S0,1240);D.sort((a,b)=>a[3]-b[3]);
const pt=(el,l)=>{try{const p=el.getPointAtLength(l);return[p.x,p.y]}catch{return[px,py]}},
fin=()=>{if(done)return;done=1;cancelAnimationFrame(rq);A.forEach(a=>a.cancel());
labels.forEach((l,i)=>l.textContent=texts[i]);dt.textContent=dS;sc.textContent=S0;[sc,pen,...cards].forEach(el=>el.removeAttribute('style'));
gh.remove();delete slot.dataset.active;H.dataset.plot='done';try{sessionStorage.setItem('plotted','1')}catch{}G&&G.fin()},
loop=()=>{const e=clk();for(let i=J.length;i--;)J[i](e)&&J.splice(i,1);let x=543,y=235,act=0;
for(const[el,a,l,st,du]of D){if(e<st){act||([x,y]=pt(el,0));break}if(e<st+du){[x,y]=pt(el,(a.effect.getComputedTiming().progress||0)*l);act=1}}
px+=(x-px)*.42;py+=(y-py)*.42;pen.setAttribute('transform',`translate(${px.toFixed(1)} ${py.toFixed(1)})`);
const r=px>860;rd.setAttribute('x',r?-16:16);rd.setAttribute('text-anchor',r?'end':'start');
rd.textContent=`X ${((px-80)/10).toFixed(1)} Y ${((py-80)/10).toFixed(1)}`;e>2820?fin():rq=raf(loop)};
on(d,'visibilitychange',()=>d.hidden&&fin());on(d,'folio:prefs',()=>ok()||fin());loop()}
// plot at once; wash in idle time after fonts (CSS wash meanwhile)
export function init({plot:p}={}){const hero=$('.hero'),svg=hero&&$('.drawing',hero);if(!hero||!ok())return;
const t0=now(),pl=p&&svg&&H.dataset.plot!='done',ma=pl&&svg.animate([],9e3),clk=()=>ma?ma.currentTime||0:now()-t0,G={g:null,fin(){this.g?.fin()}},
cssWash=()=>{if(hero.dataset.gl!='on'){delete hero.dataset.wash;pl&&$('.hero__wash',hero)?.animate({opacity:[0,1]},{duration:900,easing:EO})}},
idle=f=>w.requestIdleCallback?requestIdleCallback(f,{timeout:800}):setTimeout(f,250);
hero.dataset.wash='wait';
Promise.race([d.fonts?.ready,new Promise(r=>setTimeout(r,1200))]).then(()=>idle(()=>{G.g=wash(hero,pl,clk);G.g||cssWash()}));
setTimeout(cssWash,2200);
if(pl)plot(hero,svg,G,clk);else H.dataset.plot='done'}
// the Studio hinge lives in hinge-gl.js (it starts work only when the Studio comes near)
export const initHinge=f=>import('./hinge-gl.js').then(m=>m.initHinge(f,{ctx,prog,ok,ss,on}));
