const apiBase = '/api';
let token = localStorage.getItem('token');
let user = localStorage.getItem('user') ? JSON.parse(localStorage.getItem('user')) : null;
const i18n = {translations:{} , lang: localStorage.getItem('lang') || 'en'};

async function loadI18n(lang){
  i18n.translations = await fetch('i18n/'+lang+'.json').then(r=>r.json());
  i18n.lang = lang;
  document.querySelectorAll('[data-i18n]').forEach(el=>{
    const key = el.getAttribute('data-i18n');
    if(i18n.translations[key]) el.textContent = i18n.translations[key];
  });
}
loadI18n(i18n.lang);

document.getElementById('btnRegister').onclick = async ()=>{
  const name = document.getElementById('reg_name').value;
  const email = document.getElementById('reg_email').value;
  const password = document.getElementById('reg_password').value;
  const language = document.getElementById('reg_lang').value;
  const res = await fetch(apiBase+'/register',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,email,password,language})});
  const j = await res.json();
  if(j.token){ localStorage.setItem('token', j.token); alert('Registered'); location.reload(); } else alert(JSON.stringify(j));
};

document.getElementById('btnLogin').onclick = async ()=>{
  const email = document.getElementById('email').value;
  const password = document.getElementById('password').value;
  const res = await fetch(apiBase+'/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,password})});
  const j = await res.json();
  if(j.token){ localStorage.setItem('token', j.token); localStorage.setItem('user', JSON.stringify(j.user)); token=j.token; user=j.user; showApp(); } else alert(JSON.stringify(j));
};

function showApp(){
  document.getElementById('auth').style.display='none';
  document.getElementById('appContent').style.display='block';
  document.getElementById('langSelect').value = localStorage.getItem('lang') || 'en';
  fetchMeds();
}
if(token) showApp();

document.getElementById('btnLogout').onclick = ()=>{
  localStorage.removeItem('token'); localStorage.removeItem('user'); token=null; user=null; location.reload();
};

document.getElementById('addScheduleRow').onclick = ()=>{
  const div = document.createElement('div'); div.className='sched';
  div.innerHTML = document.querySelector('.sched').innerHTML;
  document.getElementById('schedules').appendChild(div);
};

document.getElementById('saveMed').onclick = async ()=>{
  const name = document.getElementById('med_name').value;
  const dosage = document.getElementById('med_dosage').value;
  const instructions = document.getElementById('med_instructions').value;
  const scheds = Array.from(document.querySelectorAll('.sched')).map(s=>{
    const time = s.querySelector('.sched_time').value;
    const days = Array.from(s.querySelectorAll('input[type=checkbox]:checked')).map(cb=>cb.value);
    return {time, days};
  }).filter(s=>s.time);
  const res = await fetch(apiBase+'/medicines',{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+token},body:JSON.stringify({name,dosage,instructions,schedules:scheds})});
  const j = await res.json();
  if(j.ok){ alert('Saved'); fetchMeds(); scheduleLocalAlarms(); } else alert(JSON.stringify(j));
};

async function fetchMeds(){
  const res = await fetch(apiBase+'/medicines',{headers:{'Authorization':'Bearer '+token}});
  const j = await res.json();
  const ul = document.getElementById('medList'); ul.innerHTML='';
  (j.medicines||[]).forEach(m=>{
    const li = document.createElement('li');
    li.textContent = m.name + ' — ' + (m.dosage||'') + ' ';
    if(m.schedules) li.textContent += ' [' + m.schedules.map(s=>s.time).join(',') + ']';
    ul.appendChild(li);
  });
}

document.getElementById('uploadPres').onclick = async ()=>{
  const file = document.getElementById('presFile').files[0];
  const docName = document.getElementById('docName').value;
  if(!file) return alert('choose file');
  const fd = new FormData(); fd.append('file', file); fd.append('doctor_name', docName);
  const res = await fetch(apiBase+'/upload_prescription',{method:'POST',headers:{'Authorization':'Bearer '+token},body:fd});
  const j = await res.json();
  if(j.ok) alert('Uploaded'); else alert(JSON.stringify(j));
};

document.getElementById('langSelect').onchange = (e)=>{ const v=e.target.value; localStorage.setItem('lang',v); loadI18n(v); };

// Simple client-side alarm scheduler (works while tab is open)
function scheduleLocalAlarms(){
  if(!('Notification' in window)) return;
  Notification.requestPermission();
  fetch(apiBase+'/medicines',{headers:{'Authorization':'Bearer '+token}}).then(r=>r.json()).then(j=>{
    (j.medicines||[]).forEach(m=>{
      (m.schedules||[]).forEach(s=>{
        // schedule next occurrence today at the given time (naive)
        const parts = s.time.split(':');
        const now = new Date();
        const alarm = new Date(now.getFullYear(), now.getMonth(), now.getDate(), parseInt(parts[0]), parseInt(parts[1]||0),0);
        if(alarm < now) alarm.setDate(alarm.getDate()+1);
        const ms = alarm - now;
        setTimeout(()=>{ new Notification('Time to take: ' + m.name, {body: m.dosage || ''}); }, ms);
      });
    });
  });
}
if(token) scheduleLocalAlarms();
