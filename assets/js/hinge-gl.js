// Folio 2026 · hinge-gl.js · the Studio hinge (shares the GL helpers of hero-gl.js)
// helpers are handed over by hero-gl.js, so both share one copy
let ctx,prog,ok,ss,on;
const d=document,w=window,M=Math,$=(s,r=d)=>r.querySelector(s),raf=f=>requestAnimationFrame(f);
// a painted front sweeps the UI into the painting as the frame rises to mid-screen; Kuwahara only at the front; canvas hidden at rest
// each picture is laid on the frame as object-fit:cover lays it at rest (K: its crop), so a picture of any shape keeps its proportions
const HINGE=`uniform sampler2D u_a,u_b;uniform vec2 u_res,u_tex,u_ka,u_kb;uniform float u_m;
vec2 K(vec2 p,vec2 k){return k==vec2(1.)?p:(p-.5)*k+.5;}
vec3 A(vec2 p){return texture2D(u_a,K(p,u_ka)).rgb;}vec3 B(vec2 p){return texture2D(u_b,K(p,u_kb)).rgb;}
float fr(vec2 p){return p.x*.8+(1.-p.y)*.2+(vn(p*vec2(2.5,24.))-.5)*.12+(vn(p*vec2(8.,80.))-.5)*.05;}
vec3 C(vec2 p,float t){return mix(A(p),B(p),smoothstep(.01,-.01,fr(p)-t));}
void main(){vec2 uv=gl_FragCoord.xy/u_res;uv.y=1.-uv.y;
float t=mix(-.2,1.2,u_m),e=fr(uv)-t,band=1.-smoothstep(.0,.085,abs(e+.015));
vec3 c;
if(band<.02){c=C(uv,t);}else{
float r=band*4.5,an=vn(uv*5.)*6.283;mat2 R=mat2(cos(an),sin(an),-sin(an),cos(an))*r*.34;
vec3 m0=vec3(0),m1=m0,m2=m0,m3=m0,s0=m0,s1=m0,s2=m0,s3=m0;float c0=0.,c1=0.,c2=0.,c3=0.;
for(int j=-3;j<=3;j++)for(int i=-3;i<=3;i++){vec3 k=C(uv+R*vec2(i,j)/u_tex*2.,t),q=k*k;
if(i<=0&&j<=0){m0+=k;s0+=q;c0++;}if(i>=0&&j<=0){m1+=k;s1+=q;c1++;}
if(i<=0&&j>=0){m2+=k;s2+=q;c2++;}if(i>=0&&j>=0){m3+=k;s3+=q;c3++;}}
m0/=c0;m1/=c1;m2/=c2;m3/=c3;
vec4 v=vec4(dot(s0/c0-m0*m0,vec3(1)),dot(s1/c1-m1*m1,vec3(1)),dot(s2/c2-m2*m2,vec3(1)),dot(s3/c3-m3*m3,vec3(1)));
c=m0;float b=v.x;if(v.y<b){b=v.y;c=m1;}if(v.z<b){b=v.z;c=m2;}if(v.w<b)c=m3;}
c*=1.-.1*(1.-smoothstep(0.,.012,abs(e)));
gl_FragColor=vec4(c,1);}`;
export function initHinge(fig,h){({ctx,prog,ok,ss,on}=h);const fr=fig&&$('.hinge__frame',fig),cv=fr&&$('.hinge__gl',fr),pa=fr&&$('.hinge__painting img',fr),ui=fr&&$('.hinge__ui img',fr);
if(!cv||!pa||!ui||fig.dataset.gl!=null||!ok())return;fig.dataset.gl='';
const io=new IntersectionObserver(([e])=>e.isIntersecting&&(io.disconnect(),go().catch(()=>{delete fig.dataset.gl})),{rootMargin:'100% 0px'});io.observe(fr);
async function go(){const g=ctx(cv,!1);if(!g)return;[pa,ui].forEach(i=>i.loading='eager');
const tw=M.min(2048,M.ceil(fr.clientWidth*M.min(w.devicePixelRatio||1,2)/256)*256),
tex=await Promise.all([ui,pa].map(async i=>{await i.decode();try{return await createImageBitmap(i,{resizeWidth:M.min(tw,i.naturalWidth),resizeQuality:'high'})}catch{return i}})),u=await prog(g,HINGE);
if(!u)return;
tex.forEach((t,i)=>{g.activeTexture(33984+i);g.bindTexture(3553,g.createTexture());[10242,10243].forEach(k=>g.texParameteri(3553,k,33071));
[10241,10240].forEach(k=>g.texParameteri(3553,k,9729));g.texImage2D(3553,0,6408,6408,5121,t)});
u('u_a',0);u('u_b',1);u('u_tex',[tex[0].width||tex[0].naturalWidth,tex[0].height||tex[0].naturalHeight]);
let m=0,tg=0,rq=0,vis=!d.hidden,lost=0,inv=0,first=1;
const target=()=>{const r=fr.getBoundingClientRect(),c=(r.top+r.height/2)/innerHeight;return 1-ss(.5,.95,c)},
rest=()=>{const at=m<.001?'ui':m>.999?'paint':'';at?(fig.dataset.at=at,fig.dataset.rest=''):delete fig.dataset.rest},
fit=(t,a)=>{const q=(t.width||t.naturalWidth)/(t.height||t.naturalHeight)/a;return M.abs(q-1)<.01?[1,1]:q>1?[1/q,1]:[1,q]},
draw=full=>{const r=cv.getBoundingClientRect(),k=M.min(w.devicePixelRatio||1,1.5)*(full?1:.8),W=M.max(1,M.round(r.width*k)),Ht=M.max(1,M.round(r.height*k));
(cv.width!=W||cv.height!=Ht)&&(cv.width=W,cv.height=Ht,g.viewport(0,0,W,Ht));u('u_res',[W,Ht]);u('u_ka',fit(tex[0],W/Ht));u('u_kb',fit(tex[1],W/Ht));u('u_m',m);g.drawArrays(4,0,3)},
live=()=>!lost&&vis&&ok(),
frame=()=>{rq=0;if(!live())return;m+=(tg-m)*.18;const st=M.abs(tg-m)<.002;st&&(m=tg);delete fig.dataset.rest;draw(st);st?rest():rq=raf(frame)},
kick=()=>{if(!live())return;tg=target();if(first){first=0;m=tg;draw(1);rest();return}M.abs(tg-m)>.0005&&!rq&&(rq=raf(frame))},
scroll=()=>inv&&kick();
new IntersectionObserver(([e])=>{inv=e.isIntersecting;inv&&kick()},{rootMargin:'10% 0px'}).observe(fr);
on(w,'scroll',scroll);on(w,'resize',()=>{first=1;kick()});
on(cv,'webglcontextlost',e=>{e.preventDefault();lost=1;fig.dataset.gl=''},{});
on(d,'visibilitychange',()=>{vis=!d.hidden;kick()});
on(d,'folio:prefs',()=>{fig.dataset.gl=ok()&&!lost?'on':'';first=1;kick()});
fig.dataset.gl='on';first=1;kick()}}
