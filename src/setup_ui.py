"""配置向导 Web UI — python run.py --setup 启动"""

import json, os, pathlib, threading, webbrowser, urllib.request, urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
_CONFIG_PATH = _PROJECT_ROOT / "config.yaml"
_PORT = 8765

# ---------------------------------------------------------------------------
# HTML (single-page, embedded)
# ---------------------------------------------------------------------------
_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>VoxAI 配置向导</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#1a1a2e;color:#e0e0e0;min-height:100vh;display:flex;justify-content:center;padding:2rem}
.container{max-width:640px;width:100%}
h1{text-align:center;margin-bottom:.3rem;font-size:1.6rem;color:#a78bfa}
.subtitle{text-align:center;color:#888;margin-bottom:2rem;font-size:.9rem}
.section{background:#16213e;border-radius:12px;padding:1.5rem;margin-bottom:1.2rem;border:1px solid #1a1a4e}
.section h2{font-size:1.1rem;margin-bottom:1rem;color:#7dd3fc;display:flex;align-items:center;gap:.5rem}
.row{display:flex;align-items:center;gap:.6rem;margin-bottom:.8rem}
.row label{min-width:110px;font-size:.85rem;color:#aaa;flex-shrink:0}
.row input,.row select{flex:1;padding:.45rem .6rem;border-radius:6px;border:1px solid #333;background:#0f0f23;color:#e0e0e0;font-size:.85rem}
.row input:focus,.row select:focus{outline:none;border-color:#7dd3fc}
.btn{padding:.4rem .9rem;border-radius:6px;border:none;cursor:pointer;font-size:.8rem;font-weight:600;transition:.2s}
.btn-sm{padding:.35rem .7rem;font-size:.75rem}
.btn-primary{background:#7c3aed;color:#fff}.btn-primary:hover{background:#6d28d9}
.btn-success{background:#059669;color:#fff}.btn-success:hover{background:#047857}
.btn-outline{background:transparent;border:1px solid #555;color:#ccc}.btn-outline:hover{background:#1e293b}
.badge{display:inline-block;padding:.15rem .5rem;border-radius:10px;font-size:.7rem;font-weight:600}
.badge-ok{background:#064e3b;color:#34d399}
.badge-err{background:#450a0a;color:#f87171}
.badge-wait{background:#1e1b4b;color:#a78bfa}
.status{margin-left:.5rem;font-size:.8rem}
.actions{display:flex;gap:.8rem;justify-content:center;margin-top:1.5rem}
.toast{position:fixed;top:1rem;right:1rem;padding:.8rem 1.2rem;border-radius:8px;font-size:.85rem;z-index:999;opacity:0;transition:.3s;pointer-events:none}
.toast.show{opacity:1}
.toast-ok{background:#064e3b;color:#34d399;border:1px solid #059669}
.toast-err{background:#450a0a;color:#f87171;border:1px solid #dc2626}
.deploy-list{margin-top:.5rem;display:flex;flex-wrap:wrap;gap:.4rem}
.deploy-chip{padding:.2rem .6rem;border-radius:12px;font-size:.75rem;background:#1e1b4b;color:#c4b5fd;cursor:pointer;border:1px solid #312e81}
.deploy-chip:hover{background:#312e81}
.tip{font-size:.75rem;color:#666;margin-top:.2rem;margin-left:116px}
</style></head><body>
<div class="container">
<h1>⚙️ VoxAI 配置向导</h1>
<p class="subtitle">配置你的 AI 语音输入法</p>

<div class="section">
<h2>☁️ Azure OpenAI</h2>
<div class="row"><label>Endpoint</label><input id="endpoint" placeholder="https://xxx.openai.azure.com/"></div>
<div class="row"><label>API Key</label><input id="api_key" type="password" placeholder="your-api-key"></div>
<div class="row"><label>API 版本</label><input id="api_version" value="2024-06-01"></div>
<div style="display:flex;gap:.5rem;margin:.8rem 0">
<button class="btn btn-outline btn-sm" onclick="detectDeploy()">🔍 自动检测部署</button>
<span id="detect-status"></span>
</div>
<div id="deploy-list" class="deploy-list"></div>
<div class="row"><label>转写部署</label><input id="whisper_deployment" placeholder="gpt-4o-mini-transcribe"><button class="btn btn-sm btn-outline" onclick="validate('whisper')">验证</button><span id="v-whisper" class="status"></span></div>
<div class="row"><label>润色部署</label><input id="gpt_deployment" placeholder="gpt-4o"><button class="btn btn-sm btn-outline" onclick="validate('gpt')">验证</button><span id="v-gpt" class="status"></span></div>
</div>

<div class="section">
<h2>🎙️ 录音</h2>
<div class="row"><label>麦克风</label><select id="device"><option value="">系统默认</option></select><button class="btn btn-sm btn-outline" onclick="loadDevices()">刷新</button></div>
<div class="row"><label>采样率</label><input id="sample_rate" type="number" value="16000"></div>
<div class="row"><label>最大时长(秒)</label><input id="max_duration" type="number" value="60"></div>
<div class="row"><label>静音阈值</label><input id="silence_threshold" type="number" step="0.001" value="0.01"></div>
<div class="tip">正常说话 RMS ≈ 0.02~0.2，设 0 关闭静音检测</div>
</div>

<div class="section">
<h2>⌨️ 热键</h2>
<div class="row"><label>快捷键</label><input id="combination" value="ctrl+shift+space"></div>
</div>

<div class="section">
<h2>✨ 润色 & 输出</h2>
<div class="row"><label>启用润色</label><select id="polish_enabled"><option value="true">是</option><option value="false">否</option></select></div>
<div class="row"><label>识别语言</label><input id="language" value="zh"></div>
<div class="row"><label>粘贴方式</label><select id="paste_method"><option value="auto">auto (推荐)</option><option value="pynput">pynput</option><option value="win32">win32 (仅Windows)</option><option value="clipboard">仅剪贴板</option></select></div>
</div>

<div class="actions">
<button class="btn btn-primary" onclick="saveConfig()">💾 保存配置</button>
<button class="btn btn-success" onclick="saveAndQuit()">✅ 保存并退出</button>
</div>
</div>

<div id="toast" class="toast"></div>

<script>
const $=id=>document.getElementById(id);
function toast(msg,ok=true){const t=$('toast');t.textContent=msg;t.className='toast show '+(ok?'toast-ok':'toast-err');setTimeout(()=>t.classList.remove('show'),3000)}
function badge(type){return type==='ok'?'<span class="badge badge-ok">✅ 可用</span>':type==='err'?'<span class="badge badge-err">❌ 失败</span>':'<span class="badge badge-wait">⏳</span>'}

async function api(path,body){
  const r=await fetch('/api/'+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  return r.json();
}

async function validate(which){
  const st=$('v-'+which);st.innerHTML=badge('wait');
  const dep=which==='whisper'?$('whisper_deployment').value:$('gpt_deployment').value;
  const r=await api('validate',{endpoint:$('endpoint').value,api_key:$('api_key').value,api_version:$('api_version').value,deployment:dep,type:which});
  st.innerHTML=badge(r.ok?'ok':'err');
  if(!r.ok)toast(r.error,false);
}

async function detectDeploy(){
  $('detect-status').innerHTML=badge('wait');
  const r=await api('list-deployments',{endpoint:$('endpoint').value,api_key:$('api_key').value});
  if(!r.ok){$('detect-status').innerHTML=badge('err');toast(r.error,false);return}
  $('detect-status').innerHTML=`<span class="badge badge-ok">${r.deployments.length} 个部署</span>`;
  const list=$('deploy-list');list.innerHTML='';
  r.deployments.forEach(d=>{
    const chip=document.createElement('span');chip.className='deploy-chip';chip.textContent=d.id+' ('+d.model+')';
    chip.onclick=()=>{
      if(d.model.includes('transcribe')||d.model.includes('whisper'))$('whisper_deployment').value=d.id;
      else if(d.model.includes('gpt'))$('gpt_deployment').value=d.id;
      toast('已填入: '+d.id);
    };
    list.appendChild(chip);
  });
  // Auto-fill best candidates
  const trans=r.deployments.find(d=>d.model.includes('transcribe'));
  const gpt=r.deployments.filter(d=>d.model.includes('gpt')&&!d.model.includes('transcribe')&&!d.model.includes('tts'));
  if(trans)$('whisper_deployment').value=trans.id;
  if(gpt.length){const mini=gpt.find(d=>d.model.includes('mini')&&!d.model.includes('tts'));$('gpt_deployment').value=(mini||gpt[0]).id;}
}

async function loadDevices(){
  const r=await api('list-devices',{});
  if(!r.ok){toast(r.error,false);return}
  const sel=$('device');
  const cur=sel.value;
  sel.innerHTML='<option value="">系统默认</option>';
  r.devices.forEach(d=>{const o=document.createElement('option');o.value=d.name;o.textContent=d.name+(d.default?' ⭐':'');sel.appendChild(o)});
  sel.value=cur;
}

function gatherConfig(){
  return {
    azure:{endpoint:$('endpoint').value,api_key:$('api_key').value,api_version:$('api_version').value,whisper_deployment:$('whisper_deployment').value,gpt_deployment:$('gpt_deployment').value},
    recording:{sample_rate:+$('sample_rate').value,channels:1,max_duration:+$('max_duration').value,silence_threshold:+$('silence_threshold').value,device:$('device').value||undefined},
    hotkey:{combination:$('combination').value},
    polish:{enabled:$('polish_enabled').value==='true',language:$('language').value},
    output:{paste_method:$('paste_method').value}
  };
}

async function saveConfig(){
  const r=await api('save-config',gatherConfig());
  if(r.ok)toast('配置已保存 ✅');else toast(r.error,false);
}
async function saveAndQuit(){
  const r=await api('save-config',gatherConfig());
  if(r.ok){toast('配置已保存，正在关闭...');setTimeout(()=>window.close(),1000);await api('quit',{});}
  else toast(r.error,false);
}

// Load existing config on page load
(async()=>{
  const r=await api('load-config',{});
  if(r.ok&&r.config){
    const c=r.config;
    if(c.azure){$('endpoint').value=c.azure.endpoint||'';$('api_key').value=c.azure.api_key||'';$('api_version').value=c.azure.api_version||'2024-06-01';$('whisper_deployment').value=c.azure.whisper_deployment||'';$('gpt_deployment').value=c.azure.gpt_deployment||'';}
    if(c.recording){$('sample_rate').value=c.recording.sample_rate||16000;$('max_duration').value=c.recording.max_duration||60;$('silence_threshold').value=c.recording.silence_threshold??0.01;if(c.recording.device)$('device').value=c.recording.device;}
    if(c.hotkey)$('combination').value=c.hotkey.combination||'ctrl+shift+space';
    if(c.polish){$('polish_enabled').value=c.polish.enabled===false?'false':'true';$('language').value=c.polish.language||'zh';}
    if(c.output)$('paste_method').value=c.output.paste_method||'auto';
  }
  loadDevices();
})();
</script></body></html>"""


# ---------------------------------------------------------------------------
# API handler
# ---------------------------------------------------------------------------
class _Handler(BaseHTTPRequestHandler):
    server_instance = None

    def log_message(self, *a):
        pass  # suppress logs

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(_HTML.encode())

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}
        path = self.path

        try:
            if path == "/api/validate":
                result = self._validate(body)
            elif path == "/api/list-deployments":
                result = self._list_deployments(body)
            elif path == "/api/list-devices":
                result = self._list_devices()
            elif path == "/api/save-config":
                result = self._save_config(body)
            elif path == "/api/load-config":
                result = self._load_config()
            elif path == "/api/quit":
                result = {"ok": True}
                self._send_json(result)
                threading.Thread(target=self.server_instance.shutdown, daemon=True).start()
                return
            else:
                result = {"ok": False, "error": "unknown endpoint"}
        except Exception as e:
            result = {"ok": False, "error": str(e)}

        self._send_json(result)

    def _send_json(self, obj):
        data = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(data)

    # -- API implementations --

    @staticmethod
    def _validate(body):
        import urllib.request, urllib.error, tempfile, struct
        ep = body["endpoint"].rstrip("/")
        key = body["api_key"]
        ver = body["api_version"]
        dep = body["deployment"]
        vtype = body["type"]

        if vtype == "whisper":
            # Generate a tiny valid WAV
            sr = 16000
            samples = [int(16000 * __import__("math").sin(2 * 3.14159 * 440 * i / sr)) for i in range(sr // 2)]
            wav = _make_wav(samples, sr)
            boundary = "----FormBoundary7MA4YWxkTrZu0gW"
            parts = []
            parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"test.wav\"\r\nContent-Type: audio/wav\r\n\r\n".encode() + wav)
            parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"language\"\r\n\r\nzh".encode())
            parts.append(f"--{boundary}--\r\n".encode())
            payload = b"\r\n".join(parts)
            url = f"{ep}/openai/deployments/{dep}/audio/transcriptions?api-version={ver}"
            req = urllib.request.Request(url, data=payload, headers={"api-key": key, "Content-Type": f"multipart/form-data; boundary={boundary}"})
        else:  # gpt
            payload = json.dumps({"messages": [{"role": "user", "content": "说你好"}], "max_tokens": 10}).encode()
            url = f"{ep}/openai/deployments/{dep}/chat/completions?api-version={ver}"
            req = urllib.request.Request(url, data=payload, headers={"api-key": key, "Content-Type": "application/json"})

        try:
            resp = urllib.request.urlopen(req, timeout=15)
            data = json.loads(resp.read())
            return {"ok": True, "data": str(data)[:200]}
        except urllib.error.HTTPError as e:
            err_body = e.read().decode(errors="replace")[:300]
            return {"ok": False, "error": f"HTTP {e.code}: {err_body}"}

    @staticmethod
    def _list_deployments(body):
        ep = body["endpoint"].rstrip("/")
        key = body["api_key"]
        url = f"{ep}/openai/deployments?api-version=2022-12-01"
        req = urllib.request.Request(url, headers={"api-key": key})
        try:
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read())
            deploys = [{"id": d["id"], "model": d["model"]} for d in data.get("data", [])]
            return {"ok": True, "deployments": deploys}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @staticmethod
    def _list_devices():
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            default_in = sd.default.device[0]
            result = []
            for i, d in enumerate(devices):
                if d["max_input_channels"] > 0:
                    result.append({"name": d["name"], "index": i, "default": i == default_in})
            return {"ok": True, "devices": result}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @staticmethod
    def _save_config(body):
        try:
            import yaml
        except ImportError:
            # Manual YAML generation
            yaml = None

        # Clean up empty device
        if "recording" in body and not body["recording"].get("device"):
            body["recording"].pop("device", None)

        if yaml:
            text = yaml.dump(body, allow_unicode=True, default_flow_style=False, sort_keys=False)
        else:
            text = _dict_to_yaml(body)

        _CONFIG_PATH.write_text(text, encoding="utf-8")
        return {"ok": True}

    @staticmethod
    def _load_config():
        if not _CONFIG_PATH.exists():
            return {"ok": True, "config": None}
        try:
            import yaml
            config = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8"))
            return {"ok": True, "config": config}
        except Exception as e:
            return {"ok": False, "error": str(e)}


def _make_wav(samples, sr):
    """Generate a minimal WAV file bytes."""
    import struct
    n = len(samples)
    data = struct.pack(f"<{n}h", *samples)
    header = struct.pack("<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + len(data), b"WAVE",
        b"fmt ", 16, 1, 1, sr, sr * 2, 2, 16,
        b"data", len(data))
    return header + data


def _dict_to_yaml(d, indent=0):
    """Minimal dict→YAML without PyYAML."""
    lines = []
    prefix = "    " * indent
    for k, v in d.items():
        if isinstance(v, dict):
            lines.append(f"{prefix}{k}:")
            lines.append(_dict_to_yaml(v, indent + 1))
        elif isinstance(v, bool):
            lines.append(f"{prefix}{k}: {'true' if v else 'false'}")
        elif isinstance(v, str):
            lines.append(f'{prefix}{k}: "{v}"')
        else:
            lines.append(f"{prefix}{k}: {v}")
    return "\n".join(lines)


def run_setup():
    """Launch the setup Web UI."""
    server = HTTPServer(("127.0.0.1", _PORT), _Handler)
    _Handler.server_instance = server
    url = f"http://127.0.0.1:{_PORT}"
    print(f"🔧 配置向导已启动: {url}")
    threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    print("配置向导已关闭")
