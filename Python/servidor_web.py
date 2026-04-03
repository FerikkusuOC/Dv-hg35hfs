import os
import threading
import webbrowser
import json
import uuid
import shutil
import time
import re
import subprocess
import urllib.request
from werkzeug.utils import secure_filename
from flask import Flask, render_template, jsonify, request, send_file
import motor_video
from PIL import Image, ImageOps 
from configuracoes import RESOLUCAO
import platform

# >>> SILENCIADOR SEGURO DO FLASK (CORRIGIDO) <<<
import logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR) # Silencia logs de requisição, mas não quebra o boot

# >>> CAÇADOR DE FFMPEG MULTIPLATAFORMA <<<
FFMPEG_PATH = shutil.which("ffmpeg")
if not FFMPEG_PATH:
    try:
        import imageio_ffmpeg
        FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        FFMPEG_PATH = "ffmpeg"

app = Flask(__name__)

PROJETO_ATUAL = {}
TAREFAS_RENDER = {} 
TAREFAS_UPSCALE = {}

# === CONFIGURAÇÃO DE PASTAS ===
PASTA_MIDIA = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "midia_projeto"))
if not os.path.exists(os.path.dirname(PASTA_MIDIA)) or "Python" not in __file__:
    PASTA_MIDIA = os.path.abspath("midia_projeto")

if os.path.exists(PASTA_MIDIA): shutil.rmtree(PASTA_MIDIA)
os.makedirs(PASTA_MIDIA, exist_ok=True)

PASTA_IMAGENS = os.path.abspath("imagens_finais")
PASTA_UPSCALE = os.path.join(PASTA_IMAGENS, "upscale")
os.makedirs(PASTA_IMAGENS, exist_ok=True)
os.makedirs(PASTA_UPSCALE, exist_ok=True)

PASTA_SAIDA = os.path.abspath("Saída")
PASTA_PREVIEW = os.path.join(PASTA_SAIDA, "preview")
if os.path.exists(PASTA_PREVIEW): shutil.rmtree(PASTA_PREVIEW)
os.makedirs(PASTA_PREVIEW, exist_ok=True)

PASTA_TEMP = os.path.abspath("temp_imagens")
PASTA_TEMP_THUMB = os.path.join(PASTA_TEMP, "thumb")
PASTA_TEMP_PREVIEW = os.path.join(PASTA_TEMP, "preview")

def limpar_e_pre_gerar_proxies(cenas):
    print("  [STATUS] Limpando e pré-gerando proxies (480p e Miniaturas)...")
    if os.path.exists(PASTA_TEMP): shutil.rmtree(PASTA_TEMP)
    os.makedirs(PASTA_TEMP_THUMB, exist_ok=True)
    os.makedirs(PASTA_TEMP_PREVIEW, exist_ok=True)

    for i, cena in enumerate(cenas):
        if cena is None: continue
        arq = cena.get('arquivo_origem')
        
        if arq:
            caminho_orig = os.path.join(PASTA_MIDIA, arq)
            pref = f"m_{arq}"
        else:
            caminho_orig = os.path.join(PASTA_UPSCALE, f"cena_{i:03d}.jpg")
            if not os.path.exists(caminho_orig): caminho_orig = os.path.join(PASTA_IMAGENS, f"cena_{i:03d}.jpg")
            pref = f"c_{i:03d}"

        if not os.path.exists(caminho_orig): continue
        is_video = caminho_orig.lower().endswith(('.mp4', '.webm', '.ogg', '.mov', '.mkv', '.avi'))
        is_audio = caminho_orig.lower().endswith(('.mp3', '.wav', '.m4a', '.aac', '.flac'))
        if is_audio: continue

        nome_thumb = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', f"{pref}.jpg")
        nome_prev = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', f"{pref}.mp4" if is_video else f"{pref}.jpg")
        
        path_thumb = os.path.join(PASTA_TEMP_THUMB, nome_thumb)
        path_prev = os.path.join(PASTA_TEMP_PREVIEW, nome_prev)

        try:
            if is_video:
                if not os.path.exists(path_thumb):
                    subprocess.run([FFMPEG_PATH, '-y', '-i', caminho_orig, '-ss', '00:00:00.100', '-vframes', '1', '-vf', "scale=256:256:force_original_aspect_ratio=decrease", path_thumb], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if not os.path.exists(path_prev):
                    subprocess.run([FFMPEG_PATH, '-y', '-i', caminho_orig, '-vf', "scale=854:854:force_original_aspect_ratio=decrease,pad=ceil(iw/2)*2:ceil(ih/2)*2", '-c:v', 'libx264', '-crf', '28', '-preset', 'ultrafast', '-c:a', 'aac', '-b:a', '128k', path_prev], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                img = Image.open(caminho_orig).convert('RGB')
                try: img = ImageOps.exif_transpose(img)
                except: pass
                img_thumb = img.copy(); img_thumb.thumbnail((256, 256)); img_thumb.save(path_thumb, "JPEG", quality=80)
                img_prev = img.copy(); img_prev.thumbnail((854, 854)); img_prev.save(path_prev, "JPEG", quality=80)
        except Exception as e:
            print(f"  [AVISO] Não foi possível pré-gerar proxy para {caminho_orig}: {e}")
                
    print("  [OK] Todos os proxies criados. Motor pronto!")


def iniciar_servidor(cenas_visuais, faixas_musicais, duracao_total, arquivo_audio_final, arquivo_saida):
    global PROJETO_ATUAL
    PROJETO_ATUAL = { 
        'cenas': cenas_visuais, 'faixas_musicais': faixas_musicais,
        'duracao': duracao_total, 'audio_mestre': arquivo_audio_final, 
        'saida_final': arquivo_saida, 'resolucao': RESOLUCAO 
    }
    
    limpar_e_pre_gerar_proxies(cenas_visuais)
    
    print("\n===================================================")
    print("   🌐 INICIANDO INTERFACE WEB DO MAESTRO...")
    print("===================================================")
    
    url_publica = None
    ip_senha = "Não detectado"

    if platform.system() == "Windows":
        threading.Timer(1.5, lambda: webbrowser.open("http://127.0.0.1:5000")).start()
        host_ip = '127.0.0.1'
        print(" -> [Windows] Servidor local ativado.")
    else:
        host_ip = '0.0.0.0'
        print(" -> [Colab] Cavando túnel público (Localtunnel)...")
        if os.path.exists('lt_url.txt'): os.remove('lt_url.txt')
        os.system('npx localtunnel --port 5000 > lt_url.txt 2>&1 &')
        
        for _ in range(15):
            time.sleep(2)
            if os.path.exists('lt_url.txt'):
                with open('lt_url.txt', 'r') as f:
                    match = re.search(r'(https://.*loca\.lt)', f.read())
                    if match:
                        url_publica = match.group(1)
                        break
        try:
            ip_senha = urllib.request.urlopen('https://ipv4.icanhazip.com').read().decode('utf8').strip()
        except: pass

    if url_publica:
        print("\n" + "█"*50)
        print(f"🚀 EDITOR ONLINE: {url_publica}")
        print(f"🔑 SENHA (IP):    {ip_senha}")
        print("█"*50 + "\n")

    # Inicia o Flask (Sem debug e sem reloader para evitar o erro de env)
    app.run(host=host_ip, port=5000, debug=False, use_reloader=False)

# --- ROTAS FLASK MANTIDAS ---
@app.route('/')
def painel_editor(): return render_template('index.html')

@app.route('/render_view')
def render_view(): return render_template('render_headless.html')

@app.route('/api/dados_projeto', methods=['GET'])
def obter_dados(): return jsonify(PROJETO_ATUAL)

@app.route('/api/salvar_estado', methods=['POST'])
def salvar_estado():
    dados = request.json
    global PROJETO_ATUAL
    PROJETO_ATUAL['cenas'] = dados.get('cenas', PROJETO_ATUAL['cenas'])
    PROJETO_ATUAL['faixas_musicais'] = dados.get('faixas_musicais', PROJETO_ATUAL.get('faixas_musicais', []))
    with open('estado_projeto.json', 'w', encoding='utf-8') as f: json.dump(PROJETO_ATUAL, f, indent=4, ensure_ascii=False)
    return jsonify({"status": "salvo"})

@app.route('/api/biblioteca', methods=['GET'])
def listar_biblioteca():
    extensoes_midia = ('.png', '.jpg', '.jpeg', '.webp', '.mp4', '.webm', '.ogg', '.mov', '.mkv', '.avi', '.mp3', '.wav', '.m4a', '.aac', '.flac')
    importadas = [f for f in os.listdir(PASTA_MIDIA) if f.lower().endswith(extensoes_midia)]
    geradas = [f for f in os.listdir(PASTA_IMAGENS) if os.path.isfile(os.path.join(PASTA_IMAGENS, f)) and f.lower().endswith(('.png', '.jpg', '.jpeg'))]
    return jsonify({"importadas": sorted(importadas), "geradas": sorted(geradas)})

def servir_proxy(caminho_orig, pasta_destino, prefixo, max_size, is_thumb=False):
    if not os.path.exists(caminho_orig): return "Not found", 404
    os.makedirs(pasta_destino, exist_ok=True)
    is_video = caminho_orig.lower().endswith(('.mp4', '.webm', '.ogg', '.mov', '.mkv', '.avi'))
    extensao = ".mp4" if (is_video and not is_thumb) else ".jpg"
    mimetype = "video/mp4" if (is_video and not is_thumb) else "image/jpeg"
    nome_seguro = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', f"{prefixo}{extensao}")
    caminho_proxy = os.path.join(pasta_destino, nome_seguro)
    
    if not os.path.exists(caminho_proxy):
        try:
            if is_video:
                if is_thumb: cmd = [FFMPEG_PATH, '-y', '-i', caminho_orig, '-ss', '00:00:00.100', '-vframes', '1', '-vf', f"scale={max_size[0]}:{max_size[1]}:force_original_aspect_ratio=decrease", caminho_proxy]
                else: cmd = [FFMPEG_PATH, '-y', '-i', caminho_orig, '-vf', f"scale={max_size[0]}:{max_size[1]}:force_original_aspect_ratio=decrease,pad=ceil(iw/2)*2:ceil(ih/2)*2", '-c:v', 'libx264', '-crf', '28', '-preset', 'ultrafast', '-c:a', 'aac', '-b:a', '128k', caminho_proxy]
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            else:
                img = Image.open(caminho_orig).convert('RGB')
                try: img = ImageOps.exif_transpose(img)
                except: pass
                img.thumbnail(max_size); img.save(caminho_proxy, "JPEG", quality=80)
        except: return send_file(caminho_orig, mimetype=mimetype)
    return send_file(caminho_proxy, mimetype=mimetype)

@app.route('/proxy/thumb/midia/<path:filename>')
def proxy_thumb_midia(filename): return servir_proxy(os.path.join(PASTA_MIDIA, filename), PASTA_TEMP_THUMB, f"m_{filename}", (256, 256), is_thumb=True)
@app.route('/proxy/thumb/cena/<int:idx>')
def proxy_thumb_cena(idx):
    caminho = os.path.abspath(os.path.join(PASTA_UPSCALE, f"cena_{idx:03d}.jpg"))
    if not os.path.exists(caminho): caminho = os.path.abspath(os.path.join(PASTA_IMAGENS, f"cena_{idx:03d}.jpg"))
    return servir_proxy(caminho, PASTA_TEMP_THUMB, f"c_{idx:03d}", (256, 256), is_thumb=True)
@app.route('/proxy/preview/midia/<path:filename>')
def proxy_preview_midia(filename): return servir_proxy(os.path.join(PASTA_MIDIA, filename), PASTA_TEMP_PREVIEW, f"m_{filename}", (854, 854), is_thumb=False)
@app.route('/proxy/preview/cena/<int:idx>')
def proxy_preview_cena(idx):
    caminho = os.path.abspath(os.path.join(PASTA_UPSCALE, f"cena_{idx:03d}.jpg"))
    if not os.path.exists(caminho): caminho = os.path.abspath(os.path.join(PASTA_IMAGENS, f"cena_{idx:03d}.jpg"))
    return servir_proxy(caminho, PASTA_TEMP_PREVIEW, f"c_{idx:03d}", (854, 854), is_thumb=False)

@app.route('/imagem_cena/<int:idx>')
def servir_imagem_cena(idx):
    caminho_upscale = os.path.abspath(os.path.join(PASTA_UPSCALE, f"cena_{idx:03d}.jpg"))
    caminho_orig = os.path.abspath(os.path.join(PASTA_IMAGENS, f"cena_{idx:03d}.jpg"))
    if os.path.exists(caminho_upscale): return send_file(caminho_upscale, mimetype='image/jpeg')
    return send_file(caminho_orig, mimetype='image/jpeg') if os.path.exists(caminho_orig) else ("Not found", 404)

@app.route('/midia_projeto/<filename>')
def servir_midia_projeto(filename): return send_file(os.path.join(PASTA_MIDIA, filename)) if os.path.exists(os.path.join(PASTA_MIDIA, filename)) else ("Not found", 404)
@app.route('/musicas/<path:filename>')
def servir_musica(filename): return send_file(os.path.abspath(os.path.join("musicas", filename)), mimetype='audio/mpeg')
@app.route('/api/audio_mestre')
def servir_audio_mestre(): return send_file(os.path.abspath(PROJETO_ATUAL.get('audio_mestre')))
@app.route('/sfx/transicoes/<filename>')
def servir_sfx_transicao(filename): return send_file(os.path.abspath(os.path.join("efeitos_sonoros", "transicoes", filename)), mimetype="audio/mpeg")

@app.route('/api/upload_midia', methods=['POST'])
def upload_midia():
    file = request.files['file']
    filename = secure_filename(file.filename)
    file.save(os.path.join(PASTA_MIDIA, filename))
    return jsonify({"status": "ok", "arquivo": filename})

@app.route('/api/substituir_imagem', methods=['POST'])
def substituir_imagem():
    file = request.files['file']
    idx = int(request.form.get('id_cena'))
    novo_nome = f"substituicao_cena_{idx}_{int(time.time())}.jpg"
    file.save(os.path.join(PASTA_MIDIA, novo_nome))
    return jsonify({"status": "ok", "novo_arquivo": novo_nome})

@app.route('/api/melhorar_imagem', methods=['POST'])
def melhorar_imagem_unica():
    dados = request.json
    idx = int(dados.get('id_cena'))
    cena = PROJETO_ATUAL['cenas'][idx]
    caminho_entrada = os.path.join(PASTA_MIDIA, cena['arquivo_origem']) if cena.get('arquivo_origem') else os.path.join(PASTA_IMAGENS, f"cena_{idx:03d}.jpg")
    caminho_saida = os.path.join(PASTA_UPSCALE, f"cena_{idx:03d}.jpg")
    import agente_upscale
    try: agente_upscale.aprimorar_imagem(caminho_entrada, caminho_saida)
    except: pass
    return jsonify({"status": "ok"})

@app.route('/api/melhorar_todas', methods=['POST'])
def melhorar_todas():
    task_id = str(uuid.uuid4())
    cenas_validas = [i for i, c in enumerate(PROJETO_ATUAL['cenas']) if c is not None and not c.get('is_black')]
    TAREFAS_UPSCALE[task_id] = { "estado": "processando", "progresso": 0, "atual": 0, "total": len(cenas_validas) }
    def processar_lote():
        import agente_upscale
        for idx_lote, idx_cena in enumerate(cenas_validas):
            cena = PROJETO_ATUAL['cenas'][idx_cena]
            caminho_entrada = os.path.join(PASTA_MIDIA, cena['arquivo_origem']) if cena.get('arquivo_origem') else os.path.join(PASTA_IMAGENS, f"cena_{idx_cena:03d}.jpg")
            caminho_saida = os.path.join(PASTA_UPSCALE, f"cena_{idx_cena:03d}.jpg")
            try: agente_upscale.aprimorar_imagem(caminho_entrada, caminho_saida)
            except: pass
            TAREFAS_UPSCALE[task_id]['atual'] = idx_lote + 1
            TAREFAS_UPSCALE[task_id]['progresso'] = int(((idx_lote + 1) / len(cenas_validas)) * 100)
        TAREFAS_UPSCALE[task_id]['estado'] = 'concluido'
    threading.Thread(target=processar_lote).start()
    return jsonify({"status": "iniciado", "task_id": task_id})

@app.route('/api/status_upscale/<task_id>', methods=['GET'])
def checar_status_upscale(task_id): return jsonify(TAREFAS_UPSCALE.get(task_id, {"estado": "erro"}))

@app.route('/api/renderizar_final', methods=['POST'])
def iniciar_render():
    global PROJETO_ATUAL
    dados = request.json
    PROJETO_ATUAL['cenas'] = dados.get('projeto', {}).get('cenas', PROJETO_ATUAL['cenas'])
    PROJETO_ATUAL['faixas_musicais'] = dados.get('projeto', {}).get('faixas_musicais', PROJETO_ATUAL.get('faixas_musicais', []))
    fps = int(dados.get('fps', 30))
    arquivo_final = os.path.join(PASTA_SAIDA, secure_filename(dados.get('nome_arquivo', 'Video_Final.mp4')))
    task_id = str(uuid.uuid4())
    TAREFAS_RENDER[task_id] = { "estado": "renderizando", "progresso": 0, "frame_atual": 0, "total_frames": 0, "fps": 0 }
    threading.Thread(target=lambda: motor_video.renderizar_motor_avancado(PROJETO_ATUAL, arquivo_final, fps, RESOLUCAO, task_id, TAREFAS_RENDER)).start()
    return jsonify({"status": "iniciado", "task_id": task_id})

@app.route('/api/status_render/<task_id>', methods=['GET'])
def checar_status(task_id): return jsonify(TAREFAS_RENDER.get(task_id, {"estado": "erro"}))

@app.route('/saida_video/<path:filename>')
def servir_video_final(filename): return send_file(os.path.join(PASTA_SAIDA, filename), mimetype='video/mp4')

@app.route('/api/detectar_foco_ia', methods=['POST'])
def detectar_foco_ia():
    idx = request.json.get('cena_id')
    cena = PROJETO_ATUAL['cenas'][idx]
    caminho = os.path.join(PASTA_UPSCALE, f"cena_{idx:03d}.jpg")
    if not os.path.exists(caminho): caminho = os.path.join(PASTA_IMAGENS, f"cena_{idx:03d}.jpg")
    if cena.get('arquivo_origem'): caminho = os.path.join(PASTA_MIDIA, cena['arquivo_origem'])
    try:
        import agente_visao
        b64 = agente_visao.gerar_grid_3x3_base64(caminho)
        foco = agente_visao.analisar_ponto_focal(b64, cena.get('texto_narracao', ''), cena.get('termo_busca', ''))
        PROJETO_ATUAL['cenas'][idx]['quadros_foco'] = foco if isinstance(foco, list) else [5]
        return jsonify({"status": "ok", "novo_foco": PROJETO_ATUAL['cenas'][idx]['quadros_foco']})
    except: return jsonify({"status": "erro"}), 500

@app.route('/api/musicas_biblioteca', methods=['GET'])
def listar_musicas():
    biblioteca = []
    if os.path.exists("musicas"):
        for clima in os.listdir("musicas"):
            caminho_clima = os.path.join("musicas", clima)
            if os.path.isdir(caminho_clima):
                for arquivo in os.listdir(caminho_clima):
                    if arquivo.lower().endswith(('.mp3', '.wav')):
                        duracao = 0
                        try:
                            import eyed3
                            meta = eyed3.load(os.path.join(caminho_clima, arquivo))
                            if meta and meta.info: duracao = meta.info.time_secs
                        except: pass
                        biblioteca.append({"caminho": f"musicas/{clima}/{arquivo}", "titulo": arquivo, "clima": clima, "duracao": duracao})
    return jsonify(biblioteca)

@app.route('/api/upload_musica', methods=['POST'])
def upload_musica():
    file = request.files['file']
    filename = secure_filename(file.filename)
    os.makedirs(os.path.join("musicas", "Personalizado"), exist_ok=True)
    file.save(os.path.join("musicas", "Personalizado", filename))
    return jsonify({"status": "ok", "arquivo": f"musicas/Personalizado/{filename}", "titulo": filename, "clima": "Personalizado"})
