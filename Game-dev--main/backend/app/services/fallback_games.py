"""Deterministic HTML5 game fallbacks used when AI generation fails.

Each function returns a self-contained HTML document string.
"""
from __future__ import annotations


def _fallback_platformer_game() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Platformer</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0a0a;display:flex;justify-content:center;align-items:center;min-height:100vh;
font-family:-apple-system,BlinkMacSystemFont,'SF Pro Display','Inter','Segoe UI',sans-serif;
-webkit-font-smoothing:antialiased;overflow:hidden}
canvas{display:block}
</style></head><body>
<canvas id="g"></canvas>
<script>
const C=document.getElementById('g'),X=C.getContext('2d');
let W,H;function resize(){W=C.width=innerWidth;H=C.height=innerHeight}
resize();addEventListener('resize',resize);
const K={};addEventListener('keydown',e=>K[e.code]=true);addEventListener('keyup',e=>K[e.code]=false);
const G=0.6,JUMP=-13,SPD=5;
let state='menu',score=0,lives=3,level=1,camX=0,particles=[];
let P={x:100,y:0,w:28,h:36,vx:0,vy:0,grounded:false,facing:1,frame:0,ft:0};
function mkPlatforms(lvl){
  let p=[{x:0,y:H-40,w:W*3,h:40,clr:'#2d5a27'}];
  for(let i=0;i<12+lvl*3;i++){
p.push({x:150+i*180+Math.random()*80,y:H-120-Math.random()*280,w:80+Math.random()*60,h:16,clr:'#'+['5a3a1a','4a6741','3a4a6a'][i%3]});
  }return p;
}
function mkCoins(plats){
  let c=[];plats.forEach((p,i)=>{if(i>0&&Math.random()>0.3)c.push({x:p.x+p.w/2,y:p.y-25,r:8,alive:true,t:Math.random()*6.28});});return c;
}
function mkEnemies(plats){
  let e=[];plats.forEach((p,i)=>{if(i>2&&Math.random()>0.5)e.push({x:p.x+10,y:p.y-24,w:24,h:24,vx:1.5,platform:p,alive:true});});return e;
}
let platforms,coins,enemies;
function initLevel(){platforms=mkPlatforms(level);coins=mkCoins(platforms);enemies=mkEnemies(platforms);P.x=100;P.y=H-120;P.vy=0;P.vx=0;camX=0;}
initLevel();
function burst(x,y,clr,n=10){for(let i=0;i<n;i++)particles.push({x,y,vx:(Math.random()-0.5)*4,vy:-Math.random()*5,life:1,clr,r:Math.random()*3+1});}
function update(dt){
  if(state!=='play')return;
  if(K['ArrowLeft']||K['KeyA']){P.vx=-SPD;P.facing=-1}
  else if(K['ArrowRight']||K['KeyD']){P.vx=SPD;P.facing=1}
  else P.vx*=0.8;
  if((K['Space']||K['ArrowUp']||K['KeyW'])&&P.grounded){P.vy=JUMP;P.grounded=false}
  P.vy+=G;P.x+=P.vx;P.y+=P.vy;P.grounded=false;
  platforms.forEach(p=>{if(P.x+P.w>p.x&&P.x<p.x+p.w&&P.y+P.h>=p.y&&P.y+P.h<=p.y+16&&P.vy>=0){P.y=p.y-P.h;P.vy=0;P.grounded=true}});
  if(P.y>H+100){lives--;burst(P.x,H,`#f00`,20);if(lives<=0)state='over';else{P.x=100;P.y=H-120;P.vy=0}}
  coins.forEach(c=>{if(!c.alive)return;c.t+=dt*3;let dx=P.x+P.w/2-c.x,dy=P.y+P.h/2-c.y;if(Math.sqrt(dx*dx+dy*dy)<20){c.alive=false;score+=10;burst(c.x,c.y,'#ffd700',12)}});
  enemies.forEach(e=>{if(!e.alive)return;e.x+=e.vx;if(e.x<e.platform.x||e.x+e.w>e.platform.x+e.platform.w)e.vx*=-1;
let dx=P.x-e.x,dy=P.y-e.y;if(Math.abs(dx)<P.w&&Math.abs(dy)<P.h){if(P.vy>0&&P.y<e.y){e.alive=false;P.vy=-8;score+=25;burst(e.x,e.y,'#e74c3c',15)}
else{lives--;burst(P.x,P.y,'#f00',10);P.x=100;P.y=H-120;P.vy=0;if(lives<=0)state='over'}}});
  if(coins.every(c=>!c.alive)){level++;initLevel()}
  camX+=(P.x-W/3-camX)*0.1;
  particles.forEach(p=>{p.x+=p.vx;p.y+=p.vy;p.vy+=0.15;p.life-=0.025});
  particles=particles.filter(p=>p.life>0);
  P.ft+=dt;if(P.ft>0.12){P.frame=(P.frame+1)%4;P.ft=0}
}
function drawBg(){
  let grd=X.createLinearGradient(0,0,0,H);grd.addColorStop(0,'#0b0e17');grd.addColorStop(0.5,'#1a1a2e');grd.addColorStop(1,'#16213e');
  X.fillStyle=grd;X.fillRect(0,0,W,H);
  for(let i=0;i<50;i++){X.fillStyle=`rgba(255,255,255,${0.3+Math.random()*0.5})`;X.fillRect((i*97+camX*0.05)%W,i*14%H,1.5,1.5)}
}
function drawPlayer(){
  let sx=P.x-camX,sy=P.y;X.save();X.translate(sx+P.w/2,sy+P.h/2);X.scale(P.facing,1);
  X.fillStyle='#4a90e2';X.fillRect(-P.w/2,-P.h/2,P.w,P.h);
  X.fillStyle='#3a7bd5';X.fillRect(-P.w/2,P.h/4,P.w,P.h/4);
  X.fillStyle='#fff';X.fillRect(P.facing>0?2:-10,-P.h/2+6,5,5);
  X.fillStyle='#000';X.fillRect(P.facing>0?4:-8,-P.h/2+7,2,3);
  if(!P.grounded){X.fillStyle='#4a90e2';X.fillRect(-P.w/2-3,-2,3,8);X.fillRect(P.w/2,2,3,8)}
  X.restore();
}
function draw(){
  drawBg();
  platforms.forEach(p=>{let px=p.x-camX;X.fillStyle=p.clr;X.fillRect(px,p.y,p.w,p.h);
X.fillStyle='rgba(255,255,255,0.1)';X.fillRect(px,p.y,p.w,2)});
  coins.forEach(c=>{if(!c.alive)return;let cx=c.x-camX;X.save();X.translate(cx,c.y);
X.fillStyle='#ffd700';X.shadowColor='#ffd700';X.shadowBlur=10;
X.beginPath();X.ellipse(0,0,c.r*Math.abs(Math.cos(c.t)),c.r,0,0,Math.PI*2);X.fill();
X.shadowBlur=0;X.fillStyle='#fff8dc';X.beginPath();X.ellipse(-2,-2,2,2,0,0,Math.PI*2);X.fill();X.restore()});
  enemies.forEach(e=>{if(!e.alive)return;let ex=e.x-camX;X.fillStyle='#e74c3c';
X.beginPath();X.ellipse(ex+e.w/2,e.y+e.h/2,e.w/2,e.h/2,0,0,Math.PI*2);X.fill();
X.fillStyle='#fff';X.fillRect(ex+4,e.y+6,5,5);X.fillRect(ex+e.w-9,e.y+6,5,5);
X.fillStyle='#000';X.fillRect(ex+5,e.y+8,3,3);X.fillRect(ex+e.w-8,e.y+8,3,3)});
  drawPlayer();
  particles.forEach(p=>{X.globalAlpha=p.life;X.fillStyle=p.clr;X.beginPath();X.arc(p.x-camX,p.y,p.r,0,6.28);X.fill()});
  X.globalAlpha=1;
  X.fillStyle='#fff';X.font='bold 18px system-ui';X.fillText(`Score: ${score}`,16,30);X.fillText(`Lives: ${lives}`,16,54);X.fillText(`Level: ${level}`,16,78);
  if(state==='menu'){X.fillStyle='rgba(0,0,0,0.7)';X.fillRect(0,0,W,H);X.textAlign='center';
X.font='bold 48px system-ui';X.fillStyle='#4a90e2';X.fillText('PLATFORMER',W/2,H/2-60);
X.font='20px system-ui';X.fillStyle='#aaa';X.fillText('Arrow Keys / WASD to move, Space to jump',W/2,H/2);
X.fillStyle='#fff';X.fillText('Press SPACE to Start',W/2,H/2+50);X.textAlign='left'}
  if(state==='over'){X.fillStyle='rgba(0,0,0,0.7)';X.fillRect(0,0,W,H);X.textAlign='center';
X.font='bold 48px system-ui';X.fillStyle='#e74c3c';X.fillText('GAME OVER',W/2,H/2-40);
X.font='24px system-ui';X.fillStyle='#fff';X.fillText(`Score: ${score}`,W/2,H/2+10);
X.fillText('Press SPACE to Restart',W/2,H/2+60);X.textAlign='left'}
}
function gameLoop(t){let dt=Math.min((t-(gameLoop.last||t))/1000,0.05);gameLoop.last=t;
  if(state==='menu'&&K['Space']){state='play';K['Space']=false}
  if(state==='over'&&K['Space']){state='play';score=0;lives=3;level=1;initLevel();K['Space']=false}
  update(dt);draw();requestAnimationFrame(gameLoop)}
requestAnimationFrame(gameLoop);
</script></body></html>"""

def _fallback_racing_game() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Racing</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0a0a;display:flex;justify-content:center;align-items:center;min-height:100vh;
font-family:-apple-system,BlinkMacSystemFont,'SF Pro Display','Inter','Segoe UI',sans-serif;
-webkit-font-smoothing:antialiased;overflow:hidden}
canvas{display:block}
</style></head><body>
<canvas id="g"></canvas>
<script>
const C=document.getElementById('g'),X=C.getContext('2d');
let W,H;function resize(){W=C.width=960;H=C.height=640;C.style.maxWidth='100vw';C.style.maxHeight='100vh'}
resize();
const K={};addEventListener('keydown',e=>K[e.code]=true);addEventListener('keyup',e=>K[e.code]=false);
let state='menu',lap=0,totalLaps=3,score=0,raceTime=0,driftScore=0;
const trackPts=[{x:480,y:560},{x:160,y:520},{x:80,y:380},{x:100,y:200},{x:200,y:80},{x:400,y:40},
{x:600,y:60},{x:780,y:160},{x:860,y:340},{x:820,y:480},{x:700,y:560},{x:480,y:560}];
function getTrackPoint(t){
  let i=Math.floor(t)%trackPts.length,n=(i+1)%trackPts.length,f=t-Math.floor(t);
  return{x:trackPts[i].x+(trackPts[n].x-trackPts[i].x)*f,y:trackPts[i].y+(trackPts[n].y-trackPts[i].y)*f};
}
let P={x:480,y:540,angle:-Math.PI/2,speed:0,maxSpeed:5,drift:false,driftAngle:0,tireMarks:[]};
let AI={x:480,y:560,angle:-Math.PI/2,speed:2.5,t:0.5};
let checkpointsPassed=0,checkpoints=[0.25,0.5,0.75],cpFlags=[false,false,false];
let particles=[],boosts=[{x:400,y:300,active:true},{x:700,y:200,active:true}];
function drawCar(x,y,angle,clr,isPlayer){
  X.save();X.translate(x,y);X.rotate(angle);
  // Body
  X.fillStyle=clr;X.beginPath();X.moveTo(-10,-18);X.lineTo(10,-18);X.lineTo(12,-6);X.lineTo(12,14);
  X.lineTo(8,18);X.lineTo(-8,18);X.lineTo(-12,14);X.lineTo(-12,-6);X.closePath();X.fill();
  // Windshield
  let grd=X.createLinearGradient(0,-14,0,-4);grd.addColorStop(0,'rgba(150,200,255,0.8)');grd.addColorStop(1,'rgba(100,150,200,0.3)');
  X.fillStyle=grd;X.fillRect(-7,-14,14,8);
  // Wheels
  X.fillStyle='#222';X.fillRect(-14,-14,4,8);X.fillRect(10,-14,4,8);X.fillRect(-14,8,4,8);X.fillRect(10,8,4,8);
  // Headlights
  if(isPlayer){X.fillStyle='#ffe066';X.fillRect(-8,-19,4,2);X.fillRect(4,-19,4,2)}
  // Spoiler
  X.fillStyle='#333';X.fillRect(-9,16,18,3);
  X.restore();
  // Exhaust particles
  if(isPlayer&&P.speed>2){
for(let i=0;i<2;i++)particles.push({x:x-Math.cos(angle)*20+(Math.random()-0.5)*6,
  y:y-Math.sin(angle)*20+(Math.random()-0.5)*6,vx:(Math.random()-0.5)*2,vy:(Math.random()-0.5)*2,
  life:0.5,clr:'rgba(200,200,200,',r:Math.random()*3+1});
  }
}
function drawTrack(){
  // Grass
  X.fillStyle='#1a4a1a';X.fillRect(0,0,W,H);
  // Track
  X.strokeStyle='#555';X.lineWidth=80;X.lineCap='round';X.lineJoin='round';
  X.beginPath();X.moveTo(trackPts[0].x,trackPts[0].y);
  for(let i=1;i<trackPts.length;i++)X.lineTo(trackPts[i].x,trackPts[i].y);
  X.stroke();
  // Road surface
  X.strokeStyle='#444';X.lineWidth=76;X.beginPath();X.moveTo(trackPts[0].x,trackPts[0].y);
  for(let i=1;i<trackPts.length;i++)X.lineTo(trackPts[i].x,trackPts[i].y);X.stroke();
  // Center dashes
  X.strokeStyle='#666';X.lineWidth=2;X.setLineDash([20,15]);
  X.beginPath();X.moveTo(trackPts[0].x,trackPts[0].y);
  for(let i=1;i<trackPts.length;i++)X.lineTo(trackPts[i].x,trackPts[i].y);X.stroke();
  X.setLineDash([]);
  // Start/Finish line
  X.fillStyle='#fff';for(let i=0;i<8;i++)for(let j=0;j<4;j++){
if((i+j)%2===0){X.fillRect(450+i*8,545+j*5,8,5)}}
  // Boosts
  boosts.forEach(b=>{if(!b.active)return;X.save();X.translate(b.x,b.y);
X.fillStyle='rgba(0,200,255,0.3)';X.shadowColor='#0af';X.shadowBlur=15;
X.fillRect(-12,-12,24,24);X.shadowBlur=0;X.fillStyle='#0af';X.font='bold 14px system-ui';
X.textAlign='center';X.fillText('>>',0,5);X.restore()});
}
function drawTireMarks(){P.tireMarks.forEach((m,i)=>{X.fillStyle=`rgba(40,40,40,${m.a})`;X.fillRect(m.x-1,m.y-1,3,3)})}
function distToTrack(px,py){
  let minD=Infinity;
  for(let i=0;i<trackPts.length-1;i++){
let ax=trackPts[i].x,ay=trackPts[i].y,bx=trackPts[i+1].x,by=trackPts[i+1].y;
let t=Math.max(0,Math.min(1,((px-ax)*(bx-ax)+(py-ay)*(by-ay))/((bx-ax)**2+(by-ay)**2)));
let dx=px-(ax+t*(bx-ax)),dy=py-(ay+t*(by-ay));minD=Math.min(minD,Math.sqrt(dx*dx+dy*dy));
  }return minD;
}
function update(dt){
  if(state!=='play')return;raceTime+=dt;
  let acc=K['ArrowUp']||K['KeyW']?0.12:0,brk=K['ArrowDown']||K['KeyS']?0.15:0;
  P.speed=Math.max(0,Math.min(P.maxSpeed,P.speed+acc-brk-0.02));
  let turnRate=0.04*(P.speed/P.maxSpeed);
  if(K['ArrowLeft']||K['KeyA'])P.angle-=turnRate;
  if(K['ArrowRight']||K['KeyD'])P.angle+=turnRate;
  if(K['Space']&&P.speed>2){P.drift=true;P.tireMarks.push({x:P.x,y:P.y,a:0.5});
if(P.tireMarks.length>500)P.tireMarks.shift();driftScore+=dt*100;
P.speed*=0.995;P.angle+=(K['ArrowLeft']||K['KeyA']?-0.02:K['ArrowRight']||K['KeyD']?0.02:0);
  }else P.drift=false;
  P.x+=Math.cos(P.angle)*P.speed*60*dt;P.y+=Math.sin(P.angle)*P.speed*60*dt;
  // Off-track slowdown
  if(distToTrack(P.x,P.y)>42)P.speed*=0.95;
  // Keep on screen
  P.x=Math.max(10,Math.min(W-10,P.x));P.y=Math.max(10,Math.min(H-10,P.y));
  // Boosts
  boosts.forEach(b=>{if(!b.active)return;if(Math.abs(P.x-b.x)<16&&Math.abs(P.y-b.y)<16){
P.speed=Math.min(P.maxSpeed*1.5,P.speed+3);b.active=false;setTimeout(()=>b.active=true,5000);
for(let i=0;i<15;i++)particles.push({x:b.x,y:b.y,vx:(Math.random()-0.5)*6,vy:(Math.random()-0.5)*6,life:0.8,clr:'rgba(0,170,255,',r:2})}});
  // Checkpoints
  for(let i=0;i<checkpoints.length;i++){let cp=getTrackPoint(checkpoints[i]*trackPts.length);
if(!cpFlags[i]&&Math.abs(P.x-cp.x)<30&&Math.abs(P.y-cp.y)<30){cpFlags[i]=true;checkpointsPassed++}}
  // Lap detection
  if(checkpointsPassed>=3&&Math.abs(P.x-480)<30&&Math.abs(P.y-550)<30){
lap++;cpFlags=[false,false,false];checkpointsPassed=0;score+=1000;
if(lap>=totalLaps)state='win'}
  // AI
  AI.t+=AI.speed*dt*0.15;if(AI.t>=trackPts.length)AI.t-=trackPts.length;
  let target=getTrackPoint(AI.t);AI.angle=Math.atan2(target.y-AI.y,target.x-AI.x);
  AI.x+=(target.x-AI.x)*dt*2;AI.y+=(target.y-AI.y)*dt*2;
  // Particles update
  particles.forEach(p=>{p.x+=p.vx;p.y+=p.vy;p.life-=dt*2});particles=particles.filter(p=>p.life>0);
}
function drawHUD(){
  X.fillStyle='rgba(0,0,0,0.5)';X.fillRect(10,10,200,90);
  X.fillStyle='#fff';X.font='bold 16px system-ui';
  X.fillText(`Speed: ${Math.round(P.speed*20)} km/h`,20,32);
  X.fillText(`Lap: ${Math.min(lap+1,totalLaps)} / ${totalLaps}`,20,54);
  X.fillText(`Drift: ${Math.round(driftScore)}`,20,76);
  X.fillText(`Time: ${raceTime.toFixed(1)}s`,20,96);
  // Speed bar
  X.fillStyle='#333';X.fillRect(W-160,16,140,12);
  X.fillStyle=P.speed>P.maxSpeed?'#0af':'#4a90e2';X.fillRect(W-160,16,140*(P.speed/P.maxSpeed),12);
}
function draw(){
  X.clearRect(0,0,W,H);drawTrack();drawTireMarks();
  particles.forEach(p=>{X.globalAlpha=p.life;X.fillStyle=p.clr+p.life+')';X.beginPath();X.arc(p.x,p.y,p.r,0,6.28);X.fill()});
  X.globalAlpha=1;
  drawCar(AI.x,AI.y,AI.angle,'#27ae60',false);drawCar(P.x,P.y,P.angle,'#e74c3c',true);drawHUD();
  if(state==='menu'){X.fillStyle='rgba(0,0,0,0.75)';X.fillRect(0,0,W,H);X.textAlign='center';
X.font='bold 52px system-ui';X.fillStyle='#e74c3c';X.shadowColor='#e74c3c';X.shadowBlur=20;
X.fillText('DRIFT RACER',W/2,H/2-80);X.shadowBlur=0;
X.font='20px system-ui';X.fillStyle='#ccc';
X.fillText('Arrow Keys / WASD to drive | SPACE to drift',W/2,H/2-10);
X.fillText('Complete 3 laps to win!',W/2,H/2+25);
X.fillStyle='#fff';X.fillText('Press SPACE to Start',W/2,H/2+80);X.textAlign='left'}
  if(state==='win'){X.fillStyle='rgba(0,0,0,0.75)';X.fillRect(0,0,W,H);X.textAlign='center';
X.font='bold 48px system-ui';X.fillStyle='#ffd700';X.shadowColor='#ffd700';X.shadowBlur=15;
X.fillText('YOU WIN!',W/2,H/2-40);X.shadowBlur=0;
X.font='24px system-ui';X.fillStyle='#fff';X.fillText(`Time: ${raceTime.toFixed(1)}s | Drift Score: ${Math.round(driftScore)}`,W/2,H/2+10);
X.fillText('Press SPACE to Race Again',W/2,H/2+60);X.textAlign='left'}
}
function gameLoop(t){let dt=Math.min((t-(gameLoop.last||t))/1000,0.05);gameLoop.last=t;
  if((state==='menu'||state==='win')&&K['Space']){state='play';lap=0;raceTime=0;driftScore=0;score=0;
P.x=480;P.y=540;P.angle=-Math.PI/2;P.speed=0;P.tireMarks=[];AI.t=0.5;K['Space']=false}
  update(dt);draw();requestAnimationFrame(gameLoop)}
requestAnimationFrame(gameLoop);
</script></body></html>"""

def _fallback_flappy_game() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Flappy</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0a0a;display:flex;justify-content:center;align-items:center;min-height:100vh;
font-family:-apple-system,BlinkMacSystemFont,'SF Pro Display','Inter','Segoe UI',sans-serif;
-webkit-font-smoothing:antialiased;overflow:hidden}
canvas{display:block}
</style></head><body>
<canvas id="g"></canvas>
<script>
const C=document.getElementById('g'),X=C.getContext('2d');
let W=480,H=640;C.width=W;C.height=H;
const K={};addEventListener('keydown',e=>{K[e.code]=true;if(e.code==='Space')e.preventDefault()});
addEventListener('keyup',e=>K[e.code]=false);
C.addEventListener('click',()=>flap());
let state='menu',score=0,best=0,gx=0;
let bird={x:120,y:H/2,vy:0,angle:0,wing:0};
let pipes=[],particles=[];
function resetGame(){bird.y=H/2;bird.vy=0;pipes=[];score=0;gx=0;mkPipe()}
function mkPipe(){let gap=150,gy=100+Math.random()*(H-250);pipes.push({x:W+20,gapY:gy,gapH:gap,passed:false})}
function flap(){if(state==='menu'){state='play';resetGame()}else if(state==='over'){state='play';resetGame()}
  if(state==='play'){bird.vy=-7.5;bird.wing=1}}
function update(dt){
  if(state!=='play')return;
  bird.vy+=0.35;bird.y+=bird.vy;bird.wing=Math.max(0,bird.wing-dt*8);
  bird.angle=Math.max(-0.5,Math.min(1.2,bird.vy*0.08));
  gx-=3;
  pipes.forEach(p=>{p.x-=3});
  if(pipes.length===0||pipes[pipes.length-1].x<W-200)mkPipe();
  pipes=pipes.filter(p=>p.x>-60);
  pipes.forEach(p=>{
if(!p.passed&&p.x+40<bird.x){p.passed=true;score++;best=Math.max(best,score)}
if(bird.x+14>p.x&&bird.x-14<p.x+50){if(bird.y-12<p.gapY||bird.y+12>p.gapY+p.gapH){die()}}
  });
  if(bird.y>H-50||bird.y<0)die();
}
function die(){state='over';for(let i=0;i<20;i++)particles.push({x:bird.x,y:bird.y,vx:(Math.random()-0.5)*8,vy:(Math.random()-0.5)*8,life:1,clr:'#f1c40f',r:Math.random()*3+1})}
function drawBird(x,y,angle){
  X.save();X.translate(x,y);X.rotate(angle);
  // Body
  X.fillStyle='#f1c40f';X.beginPath();X.ellipse(0,0,16,13,0,0,Math.PI*2);X.fill();
  // Wing
  let wy=bird.wing*-6;X.fillStyle='#e67e22';X.beginPath();X.ellipse(-4,wy+2,10,6,bird.wing*-0.3,0,Math.PI*2);X.fill();
  // Eye
  X.fillStyle='#fff';X.beginPath();X.arc(8,-3,5,0,Math.PI*2);X.fill();
  X.fillStyle='#000';X.beginPath();X.arc(9,-3,2.5,0,Math.PI*2);X.fill();
  // Beak
  X.fillStyle='#e74c3c';X.beginPath();X.moveTo(14,-2);X.lineTo(22,1);X.lineTo(14,4);X.closePath();X.fill();
  X.restore();
}
function drawPipe(p){
  let grd=X.createLinearGradient(p.x,0,p.x+50,0);grd.addColorStop(0,'#27ae60');grd.addColorStop(0.5,'#2ecc71');grd.addColorStop(1,'#27ae60');
  // Top pipe
  X.fillStyle=grd;X.fillRect(p.x,0,50,p.gapY);
  X.fillStyle='#219653';X.fillRect(p.x-4,p.gapY-20,58,20);
  // Bottom pipe
  X.fillStyle=grd;X.fillRect(p.x,p.gapY+p.gapH,50,H-p.gapY-p.gapH);
  X.fillStyle='#219653';X.fillRect(p.x-4,p.gapY+p.gapH,58,20);
}
function draw(){
  // Sky gradient
  let sky=X.createLinearGradient(0,0,0,H);sky.addColorStop(0,'#1a1a2e');sky.addColorStop(0.6,'#16213e');sky.addColorStop(1,'#0f3460');
  X.fillStyle=sky;X.fillRect(0,0,W,H);
  // Clouds
  X.fillStyle='rgba(255,255,255,0.05)';
  for(let i=0;i<5;i++){let cx=((i*120+gx*0.3)%600)-40;X.beginPath();X.arc(cx,60+i*40,30,0,Math.PI*2);X.arc(cx+25,55+i*40,22,0,Math.PI*2);X.fill()}
  pipes.forEach(drawPipe);
  // Ground
  X.fillStyle='#2d5a27';X.fillRect(0,H-50,W,50);
  X.fillStyle='#3a7d32';for(let i=0;i<W/20+2;i++){X.fillRect(((i*20+gx)%W+W)%W-10,H-50,20,4)}
  drawBird(bird.x,bird.y,bird.angle);
  // Particles
  particles.forEach(p=>{X.globalAlpha=p.life;X.fillStyle=p.clr;X.beginPath();X.arc(p.x,p.y,p.r,0,6.28);X.fill();
p.x+=p.vx;p.y+=p.vy;p.vy+=0.2;p.life-=0.03});
  particles=particles.filter(p=>p.life>0);X.globalAlpha=1;
  // Score
  X.textAlign='center';X.font='bold 48px system-ui';X.fillStyle='#fff';X.strokeStyle='#000';X.lineWidth=3;
  X.strokeText(score,W/2,80);X.fillText(score,W/2,80);
  if(state==='menu'){X.fillStyle='rgba(0,0,0,0.5)';X.fillRect(0,0,W,H);
X.font='bold 42px system-ui';X.fillStyle='#f1c40f';X.fillText('FLAPPY BIRD',W/2,H/2-60);
X.font='18px system-ui';X.fillStyle='#ccc';X.fillText('Press SPACE or Click to Flap',W/2,H/2);
X.fillStyle='#fff';X.fillText('Press SPACE to Start',W/2,H/2+50)}
  if(state==='over'){X.fillStyle='rgba(0,0,0,0.6)';X.fillRect(0,0,W,H);
X.font='bold 42px system-ui';X.fillStyle='#e74c3c';X.fillText('GAME OVER',W/2,H/2-50);
X.font='24px system-ui';X.fillStyle='#fff';X.fillText(`Score: ${score}  Best: ${best}`,W/2,H/2+5);
X.fillText('Press SPACE to Retry',W/2,H/2+50)}
  X.textAlign='left';
}
addEventListener('keydown',e=>{if(e.code==='Space')flap()});
function gameLoop(t){let dt=Math.min((t-(gameLoop.last||t))/1000,0.05);gameLoop.last=t;
  update(dt);draw();requestAnimationFrame(gameLoop)}
requestAnimationFrame(gameLoop);
</script></body></html>"""

def _fallback_shooter_game() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Space Shooter</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#000;display:flex;justify-content:center;align-items:center;min-height:100vh;
font-family:-apple-system,BlinkMacSystemFont,'SF Pro Display','Inter','Segoe UI',sans-serif;
-webkit-font-smoothing:antialiased;overflow:hidden}
canvas{display:block}
</style></head><body>
<canvas id="g"></canvas>
<script>
const C=document.getElementById('g'),X=C.getContext('2d');
let W=640,H=800;C.width=W;C.height=H;
const K={};addEventListener('keydown',e=>K[e.code]=true);addEventListener('keyup',e=>K[e.code]=false);
let state='menu',score=0,lives=3,wave=1,spawnTimer=0;
let P={x:W/2,y:H-80,w:32,h:32,speed:5,shootTimer:0,shootRate:0.15};
let bullets=[],enemies=[],particles=[],stars=[];
for(let i=0;i<100;i++)stars.push({x:Math.random()*W,y:Math.random()*H,s:Math.random()*2+0.5,b:Math.random()});
function spawnEnemy(){
  let t=Math.random();
  if(t<0.6)enemies.push({x:Math.random()*(W-30)+15,y:-30,w:24,h:24,vy:2+wave*0.3,hp:1,type:'small',angle:0});
  else if(t<0.9)enemies.push({x:Math.random()*(W-40)+20,y:-40,w:36,h:36,vy:1.5+wave*0.2,hp:3,type:'medium',vx:Math.sin(Date.now()*0.001)*2,angle:0});
  else enemies.push({x:Math.random()*(W-50)+25,y:-50,w:48,h:48,vy:1+wave*0.15,hp:8,type:'boss',vx:0,angle:0});
}
function burst(x,y,clr,n=12){for(let i=0;i<n;i++)particles.push({x,y,vx:(Math.random()-0.5)*6,vy:(Math.random()-0.5)*6,life:1,clr,r:Math.random()*3+1})}
function update(dt){
  if(state!=='play')return;
  if(K['ArrowLeft']||K['KeyA'])P.x-=P.speed;if(K['ArrowRight']||K['KeyD'])P.x+=P.speed;
  if(K['ArrowUp']||K['KeyW'])P.y-=P.speed;if(K['ArrowDown']||K['KeyS'])P.y+=P.speed;
  P.x=Math.max(16,Math.min(W-16,P.x));P.y=Math.max(16,Math.min(H-16,P.y));
  P.shootTimer-=dt;if((K['Space']||K['KeyZ'])&&P.shootTimer<=0){
bullets.push({x:P.x-6,y:P.y-20,vy:-10,w:3,h:12});bullets.push({x:P.x+6,y:P.y-20,vy:-10,w:3,h:12});
P.shootTimer=P.shootRate}
  bullets.forEach(b=>{b.y+=b.vy});bullets=bullets.filter(b=>b.y>-20);
  spawnTimer-=dt;if(spawnTimer<=0){spawnEnemy();spawnTimer=Math.max(0.3,1.5-wave*0.1)}
  enemies.forEach(e=>{e.y+=e.vy;if(e.vx)e.x+=Math.sin(e.y*0.02)*e.vx;e.angle+=dt*2;
if(e.y>H+50)e.hp=-1;
bullets.forEach(b=>{if(b.vy<0&&Math.abs(b.x-e.x)<e.w/2+4&&Math.abs(b.y-e.y)<e.h/2+8){e.hp--;b.vy=99;
  burst(b.x,b.y,'#ffd700',5);if(e.hp<=0){score+=e.type==='boss'?100:e.type==='medium'?30:10;
    burst(e.x,e.y,e.type==='boss'?'#e74c3c':'#ff6b6b',e.type==='boss'?30:15)}}});
if(e.hp>0&&Math.abs(P.x-e.x)<(P.w+e.w)/2&&Math.abs(P.y-e.y)<(P.h+e.h)/2){
  lives--;e.hp=0;burst(P.x,P.y,'#4a90e2',20);if(lives<=0)state='over'}
  });
  enemies=enemies.filter(e=>e.hp>0);
  if(enemies.length===0&&spawnTimer>0.5){wave++;spawnTimer=0.2}
  particles.forEach(p=>{p.x+=p.vx;p.y+=p.vy;p.life-=dt*2});particles=particles.filter(p=>p.life>0);
  stars.forEach(s=>{s.y+=s.s;if(s.y>H){s.y=0;s.x=Math.random()*W}s.b=0.3+Math.sin(Date.now()*0.003+s.x)*0.3});
}
function drawShip(x,y){
  X.save();X.translate(x,y);
  // Engine glow
  X.fillStyle='rgba(100,150,255,0.3)';X.shadowColor='#4a90e2';X.shadowBlur=15;
  X.beginPath();X.ellipse(0,18,8,12,0,0,Math.PI*2);X.fill();X.shadowBlur=0;
  // Body
  X.fillStyle='#4a90e2';X.beginPath();X.moveTo(0,-20);X.lineTo(-14,16);X.lineTo(0,10);X.lineTo(14,16);X.closePath();X.fill();
  // Cockpit
  X.fillStyle='#7ec8e3';X.beginPath();X.ellipse(0,-4,5,8,0,0,Math.PI*2);X.fill();
  // Wings
  X.fillStyle='#3a7bd5';X.beginPath();X.moveTo(-10,8);X.lineTo(-22,18);X.lineTo(-8,14);X.closePath();X.fill();
  X.beginPath();X.moveTo(10,8);X.lineTo(22,18);X.lineTo(8,14);X.closePath();X.fill();
  X.restore();
}
function drawEnemy(e){
  X.save();X.translate(e.x,e.y);
  if(e.type==='boss'){X.fillStyle='#e74c3c';X.beginPath();X.moveTo(0,-24);X.lineTo(-24,24);X.lineTo(24,24);X.closePath();X.fill();
X.fillStyle='#c0392b';X.beginPath();X.arc(0,4,10,0,Math.PI*2);X.fill();
X.fillStyle='#ff0';X.beginPath();X.arc(-6,-2,3,0,Math.PI*2);X.fill();X.beginPath();X.arc(6,-2,3,0,Math.PI*2);X.fill();
// Health bar
X.fillStyle='#333';X.fillRect(-20,-30,40,4);X.fillStyle='#e74c3c';X.fillRect(-20,-30,40*(e.hp/8),4);
  }else if(e.type==='medium'){X.fillStyle='#8e44ad';X.beginPath();X.arc(0,0,e.w/2,0,Math.PI*2);X.fill();
X.fillStyle='#fff';X.beginPath();X.arc(-6,-4,3,0,Math.PI*2);X.fill();X.beginPath();X.arc(6,-4,3,0,Math.PI*2);X.fill();
  }else{X.fillStyle='#e67e22';X.rotate(e.angle);X.fillRect(-e.w/2,-e.h/2,e.w,e.h);
X.fillStyle='#f39c12';X.fillRect(-e.w/4,-e.h/4,e.w/2,e.h/2)}
  X.restore();
}
function draw(){
  X.fillStyle='#050510';X.fillRect(0,0,W,H);
  stars.forEach(s=>{X.fillStyle=`rgba(255,255,255,${s.b})`;X.fillRect(s.x,s.y,s.s,s.s)});
  bullets.forEach(b=>{X.fillStyle='#7ec8e3';X.shadowColor='#4a90e2';X.shadowBlur=6;X.fillRect(b.x-1,b.y,b.w,b.h);X.shadowBlur=0});
  enemies.forEach(drawEnemy);
  if(state==='play')drawShip(P.x,P.y);
  particles.forEach(p=>{X.globalAlpha=p.life;X.fillStyle=p.clr;X.beginPath();X.arc(p.x,p.y,p.r,0,6.28);X.fill()});
  X.globalAlpha=1;
  X.fillStyle='#fff';X.font='bold 16px system-ui';X.fillText(`Score: ${score}`,16,28);X.fillText(`Lives: ${lives}`,16,50);X.fillText(`Wave: ${wave}`,16,72);
  if(state==='menu'){X.fillStyle='rgba(0,0,0,0.7)';X.fillRect(0,0,W,H);X.textAlign='center';
X.font='bold 48px system-ui';X.fillStyle='#4a90e2';X.shadowColor='#4a90e2';X.shadowBlur=20;
X.fillText('SPACE SHOOTER',W/2,H/2-80);X.shadowBlur=0;
X.font='18px system-ui';X.fillStyle='#aaa';X.fillText('WASD/Arrows to move | SPACE to shoot',W/2,H/2-10);
X.fillStyle='#fff';X.fillText('Press SPACE to Start',W/2,H/2+50);X.textAlign='left'}
  if(state==='over'){X.fillStyle='rgba(0,0,0,0.7)';X.fillRect(0,0,W,H);X.textAlign='center';
X.font='bold 48px system-ui';X.fillStyle='#e74c3c';X.fillText('GAME OVER',W/2,H/2-40);
X.font='24px system-ui';X.fillStyle='#fff';X.fillText(`Score: ${score} | Wave: ${wave}`,W/2,H/2+10);
X.fillText('Press SPACE to Retry',W/2,H/2+60);X.textAlign='left'}
}
function gameLoop(t){let dt=Math.min((t-(gameLoop.last||t))/1000,0.05);gameLoop.last=t;
  if((state==='menu'||state==='over')&&K['Space']){state='play';score=0;lives=3;wave=1;spawnTimer=0;
P.x=W/2;P.y=H-80;bullets=[];enemies=[];particles=[];K['Space']=false}
  update(dt);draw();requestAnimationFrame(gameLoop)}
requestAnimationFrame(gameLoop);
</script></body></html>"""

def _fallback_snake_game() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Snake</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0a0a;display:flex;justify-content:center;align-items:center;min-height:100vh;
font-family:-apple-system,BlinkMacSystemFont,'SF Pro Display','Inter','Segoe UI',sans-serif;
-webkit-font-smoothing:antialiased;overflow:hidden}
canvas{display:block}
</style></head><body>
<canvas id="g"></canvas>
<script>
const C=document.getElementById('g'),X=C.getContext('2d');
const COLS=24,ROWS=18,SZ=32;let W=C.width=COLS*SZ,H=C.height=ROWS*SZ;
const K={};addEventListener('keydown',e=>{K[e.code]=true;if(['ArrowUp','ArrowDown','ArrowLeft','ArrowRight','Space'].includes(e.code))e.preventDefault()});
addEventListener('keyup',e=>K[e.code]=false);
let state='menu',score=0,best=0,speed=8,moveTimer=0;
let snake,dir,food,particles=[];
function reset(){snake=[{x:12,y:9},{x:11,y:9},{x:10,y:9}];dir={x:1,y:0};speed=8;score=0;placeFood()}
function placeFood(){do{food={x:Math.floor(Math.random()*COLS),y:Math.floor(Math.random()*ROWS),pulse:0}}while(snake.some(s=>s.x===food.x&&s.y===food.y))}
reset();
function burst(x,y,clr,n=10){for(let i=0;i<n;i++)particles.push({x:x*SZ+SZ/2,y:y*SZ+SZ/2,vx:(Math.random()-0.5)*5,vy:(Math.random()-0.5)*5,life:1,clr,r:Math.random()*3+1})}
function update(dt){
  if(state!=='play')return;
  if((K['ArrowUp']||K['KeyW'])&&dir.y!==1){dir={x:0,y:-1}}
  if((K['ArrowDown']||K['KeyS'])&&dir.y!==-1){dir={x:0,y:1}}
  if((K['ArrowLeft']||K['KeyA'])&&dir.x!==1){dir={x:-1,y:0}}
  if((K['ArrowRight']||K['KeyD'])&&dir.x!==-1){dir={x:1,y:0}}
  moveTimer+=dt;if(moveTimer<1/speed)return;moveTimer=0;
  let head={x:snake[0].x+dir.x,y:snake[0].y+dir.y};
  if(head.x<0||head.x>=COLS||head.y<0||head.y>=ROWS||snake.some(s=>s.x===head.x&&s.y===head.y)){
state='over';best=Math.max(best,score);burst(snake[0].x,snake[0].y,'#e74c3c',25);return}
  snake.unshift(head);
  if(head.x===food.x&&head.y===food.y){score+=10;burst(food.x,food.y,'#f1c40f',15);placeFood();
if(score%50===0)speed=Math.min(20,speed+1)}
  else snake.pop();
  food.pulse+=dt*4;
}
function draw(){
  // Background grid
  X.fillStyle='#0d1117';X.fillRect(0,0,W,H);
  for(let r=0;r<ROWS;r++)for(let c=0;c<COLS;c++){X.fillStyle=(r+c)%2===0?'#0d1117':'#111820';X.fillRect(c*SZ,r*SZ,SZ,SZ)}
  // Food
  let fx=food.x*SZ+SZ/2,fy=food.y*SZ+SZ/2,fr=SZ/2-4+Math.sin(food.pulse)*2;
  X.save();X.shadowColor='#e74c3c';X.shadowBlur=12;
  X.fillStyle='#e74c3c';X.beginPath();X.arc(fx,fy,fr,0,Math.PI*2);X.fill();
  X.shadowBlur=0;X.fillStyle='#ff6b6b';X.beginPath();X.arc(fx-3,fy-3,fr*0.4,0,Math.PI*2);X.fill();X.restore();
  // Snake
  snake.forEach((s,i)=>{
let ratio=1-i/snake.length;let r=SZ/2-2-i*0.1;
let hue=120+i*3;X.fillStyle=`hsl(${hue},70%,${40+ratio*20}%)`;
X.beginPath();X.arc(s.x*SZ+SZ/2,s.y*SZ+SZ/2,Math.max(4,r),0,Math.PI*2);X.fill();
if(i===0){// Eyes
  let ex1=s.x*SZ+SZ/2+dir.x*6-dir.y*5,ey1=s.y*SZ+SZ/2+dir.y*6+dir.x*5;
  let ex2=s.x*SZ+SZ/2+dir.x*6+dir.y*5,ey2=s.y*SZ+SZ/2+dir.y*6-dir.x*5;
  X.fillStyle='#fff';X.beginPath();X.arc(ex1,ey1,3.5,0,Math.PI*2);X.fill();
  X.beginPath();X.arc(ex2,ey2,3.5,0,Math.PI*2);X.fill();
  X.fillStyle='#000';X.beginPath();X.arc(ex1+dir.x,ey1+dir.y,1.5,0,Math.PI*2);X.fill();
  X.beginPath();X.arc(ex2+dir.x,ey2+dir.y,1.5,0,Math.PI*2);X.fill();
}
  });
  // Particles
  particles.forEach(p=>{X.globalAlpha=p.life;X.fillStyle=p.clr;X.beginPath();X.arc(p.x,p.y,p.r,0,6.28);X.fill();
p.x+=p.vx;p.y+=p.vy;p.life-=0.03});particles=particles.filter(p=>p.life>0);X.globalAlpha=1;
  // HUD
  X.fillStyle='#fff';X.font='bold 18px system-ui';X.fillText(`Score: ${score}`,12,28);
  X.fillText(`Best: ${best}`,W-120,28);X.fillText(`Speed: ${speed}`,W/2-40,28);
  if(state==='menu'){X.fillStyle='rgba(0,0,0,0.75)';X.fillRect(0,0,W,H);X.textAlign='center';
X.font='bold 48px system-ui';X.fillStyle='#2ecc71';X.shadowColor='#2ecc71';X.shadowBlur=15;
X.fillText('SNAKE',W/2,H/2-60);X.shadowBlur=0;
X.font='18px system-ui';X.fillStyle='#aaa';X.fillText('Arrow Keys / WASD to steer',W/2,H/2);
X.fillStyle='#fff';X.fillText('Press SPACE to Start',W/2,H/2+50);X.textAlign='left'}
  if(state==='over'){X.fillStyle='rgba(0,0,0,0.75)';X.fillRect(0,0,W,H);X.textAlign='center';
X.font='bold 48px system-ui';X.fillStyle='#e74c3c';X.fillText('GAME OVER',W/2,H/2-40);
X.font='24px system-ui';X.fillStyle='#fff';X.fillText(`Score: ${score}  Best: ${best}`,W/2,H/2+10);
X.fillText('Press SPACE to Retry',W/2,H/2+60);X.textAlign='left'}
}
function gameLoop(t){let dt=Math.min((t-(gameLoop.last||t))/1000,0.05);gameLoop.last=t;
  if((state==='menu'||state==='over')&&K['Space']){state='play';reset();K['Space']=false}
  update(dt);draw();requestAnimationFrame(gameLoop)}
requestAnimationFrame(gameLoop);
</script></body></html>"""

