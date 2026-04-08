import os
import threading
import webbrowser
import json
import uuid
import shutil
import time
import re
import subprocess
import zipfile
from werkzeug.utils import secure_filename
from flask import Flask, request, jsonify, send_file, render_template
import motor_video
from PIL import Image, ImageOps 

from configuracoes import RESOLUCAO
import platform

# >>> NOVO: CAÇADOR DE FFMPEG MULTIPLATAFORMA (WINDOWS / LINUX / MAC) <<<
FFMPEG_PATH = shutil.which("ffmpeg")

if not FFMPEG_PATH:
    try:
        # Se não achar no sistema, usa o binário embutido da biblioteca (compatível com o OS atual)
        import imageio_ffmpeg
        FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        # Fallback genérico: tenta chamar o comando puro confiando no PATH do Linux/Windows
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

# Pastas de Proxies (Duplo Sistema)
PASTA_TEMP = os.path.abspath("temp_imagens")
PASTA_TEMP_THUMB = os.path.join(PASTA_TEMP, "thumb")
PASTA_TEMP_PREVIEW = os.path.join(PASTA_TEMP, "preview")

def limpar_e_pre_gerar_proxies(cenas):
    """Apaga os resquícios e gera todos os Proxies na inicialização (Agora com Vídeos!)"""
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

        # Identifica se a mídia original é um vídeo
        is_video = caminho_orig.lower().endswith(('.mp4', '.webm', '.ogg', '.mov', '.mkv', '.avi'))
        
        # >>> NOVA TRAVA DE SEGURANÇA: Se for áudio puro, não gera proxy visual <<<
        is_audio = caminho_orig.lower().endswith(('.mp3', '.wav', '.m4a', '.aac', '.flac'))
        if is_audio: continue

        # Ajusta as extensões: Thumb é sempre JPG. Preview de vídeo é MP4.
        nome_thumb = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', f"{pref}.jpg")
        nome_prev = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', f"{pref}.mp4" if is_video else f"{pref}.jpg")
        
        path_thumb = os.path.join(PASTA_TEMP_THUMB, nome_thumb)
        path_prev = os.path.join(PASTA_TEMP_PREVIEW, nome_prev)

        try:
            if is_video:
                # 1. Extrai o 1º frame do vídeo usando FFmpeg (Miniatura JPG)
                if not os.path.exists(path_thumb):
                    subprocess.run([FFMPEG_PATH, '-y', '-i', caminho_orig, '-ss', '00:00:00.100', '-vframes', '1', '-vf', "scale=256:256:force_original_aspect_ratio=decrease", path_thumb], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                # 2. Comprime o vídeo para um Proxy 480p super leve (Preview MP4)
                if not os.path.exists(path_prev):
                    subprocess.run([FFMPEG_PATH, '-y', '-i', caminho_orig, '-vf', "scale=854:854:force_original_aspect_ratio=decrease,pad=ceil(iw/2)*2:ceil(ih/2)*2", '-c:v', 'libx264', '-crf', '28', '-preset', 'ultrafast', '-c:a', 'aac', '-b:a', '128k', path_prev], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                # Código padrão rápido do PIL para Imagens
                img = Image.open(caminho_orig).convert('RGB')
                try: img = ImageOps.exif_transpose(img)
                except: pass
                
                img_thumb = img.copy()
                img_thumb.thumbnail((256, 256))
                img_thumb.save(path_thumb, "JPEG", quality=80)
                
                img_prev = img.copy()
                img_prev.thumbnail((854, 854))
                img_prev.save(path_prev, "JPEG", quality=80)
        except Exception as e:
            print(f"  [AVISO] Não foi possível pré-gerar proxy para {caminho_orig}: {e}")
                
    print("  [OK] Todos os proxies criados. Motor pronto!")


def iniciar_servidor(cenas_visuais, faixas_musicais, duracao_total, arquivo_audio_final, arquivo_saida):
    global PROJETO_ATUAL
    PROJETO_ATUAL = { 
        'cenas': cenas_visuais, 
        'faixas_musicais': faixas_musicais,
        'duracao': duracao_total, 
        'audio_mestre': arquivo_audio_final, 
        'saida_final': arquivo_saida, 
        'resolucao': RESOLUCAO 
    }
    
    limpar_e_pre_gerar_proxies(cenas_visuais)
    
    # --- SILENCIADOR DE LOGS (FLASK/WERKZEUG) ---
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    
    print("\n===================================================")
    print("   🌐 INICIANDO INTERFACE WEB DO MINDKUT...")
    print("===================================================")
    
    url_publica = None

    if platform.system() == "Windows":
        threading.Timer(1.5, lambda: webbrowser.open("http://127.0.0.1:5000")).start()
        host_ip = '127.0.0.1'
        print(" -> [Windows] Servidor local ativado.")
    else:
        host_ip = '0.0.0.0'
        print(" -> [Colab] Utilizando o túnel blindado nativo do Google...")
        
        # Lê o link seguro que o Colab gerou em segredo no início da execução
        if os.path.exists('colab_url.txt'):
            with open('colab_url.txt', 'r') as f:
                url_publica = f.read().strip()

    if url_publica:
        print("\n" + "█"*50)
        print(f"🚀 EDITOR ONLINE: {url_publica}")
        print("█"*50 + "\n")
    elif platform.system() != "Windows":
        print("\n[AVISO] Não foi possível resgatar o link do Google Colab.")

    # Inicia o Flask
    app.run(host=host_ip, port=5000, debug=False, use_reloader=False)

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
    PROJETO_ATUAL['cenas'] = dados.get('cenas', PROJETO_ATUAL.get('cenas', []))
    PROJETO_ATUAL['faixas_musicais'] = dados.get('faixas_musicais', PROJETO_ATUAL.get('faixas_musicais', []))
    
    # A MÁGICA: Agora o Python salva os volumes e a duração também!
    if 'volumes_camadas' in dados: PROJETO_ATUAL['volumes_camadas'] = dados['volumes_camadas']
    if 'volume_locucao' in dados: PROJETO_ATUAL['volume_locucao'] = dados['volume_locucao']
    if 'duracao' in dados: PROJETO_ATUAL['duracao'] = dados['duracao']
    
    with open('estado_projeto.json', 'w', encoding='utf-8') as f: json.dump(PROJETO_ATUAL, f, indent=4, ensure_ascii=False)
    return jsonify({"status": "salvo"})

@app.route('/api/biblioteca', methods=['GET'])
def listar_biblioteca():
    extensoes_midia = ('.png', '.jpg', '.jpeg', '.webp', '.mp4', '.webm', '.ogg', '.mov', '.mkv', '.avi', '.mp3', '.wav', '.m4a', '.aac', '.flac')
    importadas = [f for f in os.listdir(PASTA_MIDIA) if f.lower().endswith(extensoes_midia)]
    
    geradas = [f for f in os.listdir(PASTA_IMAGENS) if os.path.isfile(os.path.join(PASTA_IMAGENS, f)) and f.lower().endswith(('.png', '.jpg', '.jpeg'))]
    return jsonify({"importadas": sorted(importadas), "geradas": sorted(geradas)})

# === SISTEMA DINÂMICO DE PROXIES (BLINDADO) ===
def servir_proxy(caminho_orig, pasta_destino, prefixo, max_size, is_thumb=False):
    if not os.path.exists(caminho_orig): return "Not found", 404
    os.makedirs(pasta_destino, exist_ok=True)
    
    is_video = caminho_orig.lower().endswith(('.mp4', '.webm', '.ogg', '.mov', '.mkv', '.avi'))
    
    # Se for thumbnail, forçamos saída em .jpg. Se for preview de vídeo, forçamos .mp4
    extensao = ".mp4" if (is_video and not is_thumb) else ".jpg"
    mimetype = "video/mp4" if (is_video and not is_thumb) else "image/jpeg"
    
    nome_seguro = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', f"{prefixo}{extensao}")
    caminho_proxy = os.path.join(pasta_destino, nome_seguro)
    
    precisa_gerar = True
    if os.path.exists(caminho_proxy):
        try:
            if os.path.getmtime(caminho_orig) <= os.path.getmtime(caminho_proxy):
                precisa_gerar = False
        except: pass
            
    if precisa_gerar:
        try:
            if is_video:
                if is_thumb:
                    # Gera miniatura da imagem do vídeo na hora
                    cmd = [FFMPEG_PATH, '-y', '-i', caminho_orig, '-ss', '00:00:00.100', '-vframes', '1', '-vf', f"scale={max_size[0]}:{max_size[1]}:force_original_aspect_ratio=decrease", caminho_proxy]
                else:
                    # Gera proxy mp4 otimizado
                    cmd = [FFMPEG_PATH, '-y', '-i', caminho_orig, '-vf', f"scale={max_size[0]}:{max_size[1]}:force_original_aspect_ratio=decrease,pad=ceil(iw/2)*2:ceil(ih/2)*2", '-c:v', 'libx264', '-crf', '28', '-preset', 'ultrafast', '-c:a', 'aac', '-b:a', '128k', caminho_proxy]
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            else:
                img = Image.open(caminho_orig).convert('RGB')
                try: img = ImageOps.exif_transpose(img)
                except: pass
                img.thumbnail(max_size) 
                img.save(caminho_proxy, "JPEG", quality=80)
        except Exception as e:
            print(f"[ERRO PROXY] Falha ao gerar {nome_seguro}: {e}. Retornando original.")
            # Rede de segurança: Se falhar a compressão, entrega o vídeo pesado original pro navegador não quebrar
            mimetype_fallback = "video/mp4" if is_video else "image/jpeg"
            return send_file(caminho_orig, mimetype=mimetype_fallback)
            
    return send_file(caminho_proxy, mimetype=mimetype)

@app.route('/proxy/thumb/midia/<path:filename>')
def proxy_thumb_midia(filename):
    return servir_proxy(os.path.join(PASTA_MIDIA, filename), PASTA_TEMP_THUMB, f"m_{filename}", (256, 256), is_thumb=True)

@app.route('/proxy/thumb/cena/<int:idx>')
def proxy_thumb_cena(idx):
    caminho = os.path.abspath(os.path.join(PASTA_UPSCALE, f"cena_{idx:03d}.jpg"))
    if not os.path.exists(caminho): caminho = os.path.abspath(os.path.join(PASTA_IMAGENS, f"cena_{idx:03d}.jpg"))
    return servir_proxy(caminho, PASTA_TEMP_THUMB, f"c_{idx:03d}", (256, 256), is_thumb=True)

@app.route('/proxy/preview/midia/<path:filename>')
def proxy_preview_midia(filename):
    return servir_proxy(os.path.join(PASTA_MIDIA, filename), PASTA_TEMP_PREVIEW, f"m_{filename}", (854, 854), is_thumb=False)

@app.route('/proxy/preview/cena/<int:idx>')
def proxy_preview_cena(idx):
    caminho = os.path.abspath(os.path.join(PASTA_UPSCALE, f"cena_{idx:03d}.jpg"))
    if not os.path.exists(caminho): caminho = os.path.abspath(os.path.join(PASTA_IMAGENS, f"cena_{idx:03d}.jpg"))
    return servir_proxy(caminho, PASTA_TEMP_PREVIEW, f"c_{idx:03d}", (854, 854), is_thumb=False)


# Rotas auxiliares
@app.route('/imagem_cena/<int:idx>')
def servir_imagem_cena(idx):
    caminho_upscale = os.path.abspath(os.path.join(PASTA_UPSCALE, f"cena_{idx:03d}.jpg"))
    caminho_orig = os.path.abspath(os.path.join(PASTA_IMAGENS, f"cena_{idx:03d}.jpg"))
    if os.path.exists(caminho_upscale): return send_file(caminho_upscale, mimetype='image/jpeg')
    elif os.path.exists(caminho_orig): return send_file(caminho_orig, mimetype='image/jpeg')
    return "Imagem não encontrada", 404

@app.route('/midia_projeto/<filename>')
def servir_midia_projeto(filename):
    caminho = os.path.join(PASTA_MIDIA, filename)
    if os.path.exists(caminho): return send_file(caminho)
    return "Mídia não encontrada", 404

@app.route('/musicas/<path:filename>')
def servir_musica(filename):
    caminho = os.path.abspath(os.path.join("musicas", filename))
    if os.path.exists(caminho): 
        return send_file(caminho, mimetype='audio/mpeg')
    return "Música não encontrada", 404

@app.route('/api/audio_mestre')
def servir_audio_mestre():
    audio_path = PROJETO_ATUAL.get('audio_mestre')
    if audio_path:
        caminho_abs = os.path.abspath(audio_path)
        if not os.path.exists(caminho_abs): caminho_abs = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", audio_path))
        if os.path.exists(caminho_abs): return send_file(caminho_abs)
    return "Áudio não encontrado", 404

@app.route('/sfx/transicoes/<filename>')
def servir_sfx_transicao(filename):
    caminho = os.path.abspath(os.path.join("efeitos_sonoros", "transicoes", filename))
    if os.path.exists(caminho): return send_file(caminho, mimetype="audio/mpeg")
    return "SFX não encontrado", 404

@app.route('/api/upload_midia', methods=['POST'])
def upload_midia():
    if 'file' not in request.files: return jsonify({"erro": "Nenhum arquivo"}), 400
    file = request.files['file']
    filename = secure_filename(file.filename)
    file.save(os.path.join(PASTA_MIDIA, filename))
    return jsonify({"status": "ok", "arquivo": filename})

@app.route('/api/substituir_imagem', methods=['POST'])
def substituir_imagem():
    if 'file' not in request.files: return jsonify({"erro": "Nenhum arquivo"}), 400
    file = request.files['file']
    idx = int(request.form.get('id_cena'))
    
    novo_nome = f"substituicao_cena_{idx}_{int(time.time())}.jpg"
    caminho_alvo = os.path.join(PASTA_MIDIA, novo_nome)
    file.save(caminho_alvo)
    
    return jsonify({"status": "ok", "novo_arquivo": novo_nome})

@app.route('/api/melhorar_imagem', methods=['POST'])
def melhorar_imagem_unica():
    dados = request.json
    idx = int(dados.get('id_cena'))
    cena = PROJETO_ATUAL['cenas'][idx]
    caminho_entrada = os.path.join(PASTA_MIDIA, cena['arquivo_origem']) if cena.get('arquivo_origem') else os.path.join(PASTA_IMAGENS, f"cena_{idx:03d}.jpg")
    caminho_saida = os.path.join(PASTA_UPSCALE, f"cena_{idx:03d}.jpg")
    
    if os.path.exists(caminho_entrada):
        import agente_upscale
        try: agente_upscale.aprimorar_imagem(caminho_entrada, caminho_saida)
        except Exception as e: print(f"[Erro Upscale IA] {e}")
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
            
            if os.path.exists(caminho_entrada):
                try: agente_upscale.aprimorar_imagem(caminho_entrada, caminho_saida)
                except: pass
            
            TAREFAS_UPSCALE[task_id]['atual'] = idx_lote + 1
            TAREFAS_UPSCALE[task_id]['progresso'] = int(((idx_lote + 1) / len(cenas_validas)) * 100)
        TAREFAS_UPSCALE[task_id]['estado'] = 'concluido'

    threading.Thread(target=processar_lote).start()
    return jsonify({"status": "iniciado", "task_id": task_id})

@app.route('/api/status_upscale/<task_id>', methods=['GET'])
def checar_status_upscale(task_id):
    if task_id in TAREFAS_UPSCALE: return jsonify(TAREFAS_UPSCALE[task_id])
    return jsonify({"estado": "erro"}), 404

@app.route('/api/renderizar_final', methods=['POST'])
def iniciar_render():
    global PROJETO_ATUAL
    dados = request.json
    projeto_req = dados.get('projeto', {})
    
    PROJETO_ATUAL['cenas'] = projeto_req.get('cenas', PROJETO_ATUAL.get('cenas', []))
    PROJETO_ATUAL['faixas_musicais'] = projeto_req.get('faixas_musicais', PROJETO_ATUAL.get('faixas_musicais', []))
    
    # Garantindo que o motor de renderização receba os volumes atualizados
    if 'volumes_camadas' in projeto_req: PROJETO_ATUAL['volumes_camadas'] = projeto_req['volumes_camadas']
    if 'volume_locucao' in projeto_req: PROJETO_ATUAL['volume_locucao'] = projeto_req['volume_locucao']
    if 'duracao' in projeto_req: PROJETO_ATUAL['duracao'] = projeto_req['duracao']
    
    fps_escolhido = int(dados.get('fps', 30))
    
    fps_escolhido = int(dados.get('fps', 30))
    resolucao_escolhida = dados.get('resolucao', RESOLUCAO)
    nome_arquivo = dados.get('nome_arquivo', 'Video_Final.mp4')
    if not nome_arquivo.endswith('.mp4'): nome_arquivo += '.mp4'
    
    arquivo_final = os.path.join(PASTA_SAIDA, secure_filename(nome_arquivo))
    task_id = str(uuid.uuid4())
    
    TAREFAS_RENDER[task_id] = { "estado": "renderizando", "progresso": 0, "frame_atual": 0, "total_frames": 0, "fps": 0 }
    threading.Thread(target=lambda: motor_video.renderizar_motor_avancado(PROJETO_ATUAL, arquivo_final, fps_escolhido, resolucao_escolhida, task_id, TAREFAS_RENDER)).start()
    return jsonify({"status": "iniciado", "task_id": task_id})

@app.route('/api/status_render/<task_id>', methods=['GET'])
def checar_status(task_id):
    if task_id in TAREFAS_RENDER: return jsonify(TAREFAS_RENDER[task_id])
    return jsonify({"estado": "erro"}), 404

@app.route('/saida_video/<path:filename>')
def servir_video_final(filename):
    caminho = os.path.abspath(os.path.join(PASTA_SAIDA, filename))
    if os.path.exists(caminho): return send_file(caminho, mimetype='video/mp4')
    return "Vídeo não encontrado", 404

@app.route('/api/detectar_foco_ia', methods=['POST'])
def detectar_foco_ia():
    dados = request.json
    idx = dados.get('cena_id')
    cena = PROJETO_ATUAL['cenas'][idx]
    
    caminho_imagem = os.path.join(PASTA_UPSCALE, f"cena_{idx:03d}.jpg")
    if not os.path.exists(caminho_imagem): caminho_imagem = os.path.join(PASTA_IMAGENS, f"cena_{idx:03d}.jpg")
    if cena.get('arquivo_origem'): caminho_imagem = os.path.join(PASTA_MIDIA, cena['arquivo_origem'])
        
    try:
        import agente_visao
        b64_img = agente_visao.gerar_grid_3x3_base64(caminho_imagem)
        novo_foco = agente_visao.analisar_ponto_focal(b64_img, cena.get('texto_narracao', ''), cena.get('termo_busca', ''))
        if not isinstance(novo_foco, list) or len(novo_foco) == 0: novo_foco = [5]
        PROJETO_ATUAL['cenas'][idx]['quadros_foco'] = novo_foco
        return jsonify({"status": "ok", "novo_foco": novo_foco})
    except: return jsonify({"status": "erro"}), 500

import eyed3 # Para ler a duração dos MP3 (adicione ao pip install)

@app.route('/api/musicas_biblioteca', methods=['GET'])
def listar_musicas():
    biblioteca = []
    pasta_base = os.path.abspath("musicas")
    
    if os.path.exists(pasta_base):
        for clima in os.listdir(pasta_base):
            caminho_clima = os.path.join(pasta_base, clima)
            if os.path.isdir(caminho_clima):
                for arquivo in os.listdir(caminho_clima):
                    if arquivo.lower().endswith(('.mp3', '.wav', '.ogg', '.m4a')):
                        caminho_completo = os.path.join(caminho_clima, arquivo)
                        duracao = 0
                        try:
                            if arquivo.lower().endswith('.mp3'):
                                import eyed3
                                eyed3.log.setLevel("ERROR")
                                audio_meta = eyed3.load(caminho_completo)
                                if audio_meta and audio_meta.info:
                                    duracao = audio_meta.info.time_secs
                        except: 
                            pass
                        
                        biblioteca.append({
                            "caminho": f"musicas/{clima}/{arquivo}".replace('\\', '/'),
                            "titulo": arquivo,
                            "clima": clima,
                            "duracao": duracao
                        })
    return jsonify(biblioteca)

@app.route('/api/upload_musica', methods=['POST'])
def upload_musica():
    if 'file' not in request.files: return jsonify({"erro": "Nenhum arquivo"}), 400
    file = request.files['file']
    filename = secure_filename(file.filename)
    
    pasta_alvo = os.path.join("musicas", "Personalizado")
    os.makedirs(pasta_alvo, exist_ok=True)
    caminho_salvo = os.path.join(pasta_alvo, filename)
    file.save(caminho_salvo)
    
    return jsonify({"status": "ok", "arquivo": f"musicas/Personalizado/{filename}", "titulo": filename, "clima": "Personalizado"})

# =====================================================================
# SISTEMA DE ARQUIVOS .MINDKUT (EXPORTAR / IMPORTAR)
# =====================================================================

STATUS_EXPORTACAO = {"progresso": 0, "estado": "ocioso", "arquivo": ""}

def _gerar_zip_projeto(nome_zip):
    global STATUS_EXPORTACAO
    STATUS_EXPORTACAO = {"progresso": 0, "estado": "processando", "arquivo": ""}
    
    # Normaliza os nomes para o SO atual (Windows/Linux)
    pastas_alvo = [os.path.normpath(p) for p in ["entrada", "imagens finais", "midia_projeto", "musicas/personalizado", "temp_imagens"]]
    arquivos_alvo = ["estado_projeto.json"]
    
    # 1. Mapeamento inicial de arquivos para garantir que nada seja esquecido
    lista_para_zipar = []
    for arq in arquivos_alvo:
        if os.path.exists(arq):
            lista_para_zipar.append(arq)
    
    for pasta in pastas_alvo:
        if os.path.exists(pasta):
            # O os.walk percorre inclusive subpastas criadas pela IA ou usuário
            for root, _, files in os.walk(pasta):
                for f in files:
                    caminho_completo = os.path.join(root, f)
                    lista_para_zipar.append(caminho_completo)
    
    total = len(lista_para_zipar)
    if total == 0: total = 1 # Evita divisão por zero
    
    os.makedirs("Saida", exist_ok=True)
    caminho_zip = os.path.join("Saida", f"{nome_zip}.mindkut")
    
    try:
        # 2. Empacotamento real
        with zipfile.ZipFile(caminho_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for i, caminho_arquivo in enumerate(lista_para_zipar):
                # Mantém a estrutura de pastas idêntica ao projeto original
                arcname = os.path.relpath(caminho_arquivo, start=".")
                zipf.write(caminho_arquivo, arcname)
                
                # Atualiza o progresso para a barra de interface
                STATUS_EXPORTACAO["progresso"] = int(((i + 1) / total) * 100)
                
        STATUS_EXPORTACAO["progresso"] = 100
        STATUS_EXPORTACAO["estado"] = "concluido"
        STATUS_EXPORTACAO["arquivo"] = caminho_zip
        print(f"      [SUCESSO] Projeto '{nome_zip}' exportado com {total} arquivos.")
        
    except Exception as e:
        STATUS_EXPORTACAO["estado"] = "erro"
        print(f"      [ERRO] Falha ao exportar projeto: {e}")

@app.route('/api/iniciar_exportacao', methods=['POST'])
def iniciar_exportacao():
    dados = request.json
    nome = dados.get('nome', 'Meu_Projeto')
    # Limpa caracteres inválidos para evitar erro no Windows/Linux
    nome = re.sub(r'[^\w\s-]', '', nome).strip().replace(' ', '_')
    if not nome: nome = "Projeto_MindKut"
    threading.Thread(target=_gerar_zip_projeto, args=(nome,)).start()
    return jsonify({"status": "iniciado"})

@app.route('/api/status_exportacao', methods=['GET'])
def status_exportacao():
    return jsonify(STATUS_EXPORTACAO)

@app.route('/api/download_projeto')
def download_projeto():
    caminho = request.args.get('arquivo')
    
    if caminho and os.path.exists(caminho):
        # Converte o caminho relativo para o caminho absoluto seguro do sistema
        caminho_absoluto = os.path.abspath(caminho)
        try:
            return send_file(caminho_absoluto, as_attachment=True)
        except Exception as e:
            return f"Erro interno ao tentar enviar o arquivo: {str(e)}", 500
            
    return "Arquivo de projeto não encontrado no servidor.", 404

@app.route('/api/importar_projeto', methods=['POST'])
def importar_projeto():
    if 'file' not in request.files: return jsonify({"erro": "Nenhum arquivo enviado"}), 400
    file = request.files['file']
    if file.filename == '': return jsonify({"erro": "Nome de arquivo vazio"}), 400
    
    temp_zip = "temp_import.mindkut"
    file.save(temp_zip)
    
    # 1. Limpeza Agressiva: Apaga o projeto antigo da memória e do disco
    pastas_alvo = ["entrada", "imagens finais", "midia_projeto", "musicas/personalizado", "temp_imagens"]
    for pasta in pastas_alvo:
        if os.path.exists(pasta):
            shutil.rmtree(pasta)
        os.makedirs(pasta, exist_ok=True)
        
    # 2. Descompactação do novo projeto
    with zipfile.ZipFile(temp_zip, 'r') as zipf:
        zipf.extractall(".")
        
    os.remove(temp_zip)
    
    # 3. Recarrega o estado em memória para o Python
    global PROJETO_ATUAL
    if os.path.exists("estado_projeto.json"):
        with open("estado_projeto.json", "r", encoding="utf-8") as f:
            PROJETO_ATUAL = json.load(f)
            
    return jsonify({"status": "ok"})
